import threading
from queue import Empty, Queue

from wappalyzer.browser.analyzer import (
    DriverPool,
    cookie_to_cookies,
    merge_technologies,
    process_url,
)
from wappalyzer.core.analyzer import http_scan


class Wappalyzer:
    SUPPORTED_SCAN_TYPES = {"fast", "balanced", "full"}
    MAX_BROWSER_WORKERS = 3

    def __init__(self, scan_type="full", workers=1, cookie=None, timeout=30):
        scan_type = scan_type.lower()

        if scan_type not in self.SUPPORTED_SCAN_TYPES:
            raise ValueError(
                f"Unsupported scan_type {scan_type!r}. "
                f"Expected one of: {', '.join(sorted(self.SUPPORTED_SCAN_TYPES))}"
            )

        if workers < 1:
            raise ValueError("workers must be at least 1")

        if timeout < 1:
            raise ValueError("timeout must be at least 1 second")

        self.scan_type = scan_type
        self.workers = workers
        self.cookie = cookie
        self.timeout = timeout
        self._driver_pool = None
        self._driver_pool_size = 0
        self._closed = False
        self._lock = threading.RLock()

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        with self._lock:
            if self._closed:
                return

            self._closed = True
            driver_pool = self._driver_pool
            self._driver_pool = None
            self._driver_pool_size = 0

        if driver_pool:
            driver_pool.cleanup()

    def analyze(self, url, cookie=None):
        result_url, technologies = self._analyze_url(url, cookie)

        return {result_url: technologies}

    def analyze_many(self, urls, cookie=None, on_result=None, on_error=None):
        urls = [url for url in urls if url]

        if not urls:
            return {}

        worker_count = self._worker_count(len(urls))

        if self.scan_type == "full":
            self._ensure_driver_pool(worker_count)

        url_queue = Queue()
        result_queue = Queue()
        stop_event = threading.Event()
        results = {}

        for url in urls:
            url_queue.put(url)

        def worker():
            while not stop_event.is_set():
                try:
                    original_url = url_queue.get_nowait()
                except Empty:
                    break

                result_url = original_url
                technologies = {}
                error = None

                try:
                    result_url, technologies = self._analyze_url(original_url, cookie)
                except Exception as exc:
                    error = exc
                finally:
                    result_queue.put((result_url, technologies or {}, error))
                    url_queue.task_done()

        threads = [
            threading.Thread(target=worker)
            for _ in range(worker_count)
        ]
        interrupted = False
        processed = 0

        for thread in threads:
            thread.start()

        try:
            while processed < len(urls):
                try:
                    result_url, technologies, error = result_queue.get(timeout=0.1)
                except Empty:
                    if all(not thread.is_alive() for thread in threads):
                        break

                    continue

                processed += 1
                results[result_url] = technologies

                if error and on_error:
                    on_error(result_url, error)

                if on_result:
                    on_result(result_url, technologies)

                result_queue.task_done()
        except KeyboardInterrupt:
            interrupted = True
            stop_event.set()
        finally:
            for thread in threads:
                thread.join()

            while not result_queue.empty():
                result_url, technologies, error = result_queue.get()
                results[result_url] = technologies

                if error and on_error:
                    on_error(result_url, error)

                if on_result:
                    on_result(result_url, technologies)

                result_queue.task_done()

        if interrupted:
            raise KeyboardInterrupt

        return results

    def _check_open(self):
        if self._closed:
            raise RuntimeError("Wappalyzer scanner is closed")

    def _worker_count(self, url_count):
        if self.scan_type == "full":
            return min(self.workers, self.MAX_BROWSER_WORKERS, url_count)

        return min(self.workers, url_count)

    def _browser_worker_count(self):
        return min(self.workers, self.MAX_BROWSER_WORKERS)

    def _ensure_driver_pool(self, size):
        with self._lock:
            self._check_open()

            if self._driver_pool:
                if size > self._driver_pool_size:
                    self._driver_pool.grow_to(size)
                    self._driver_pool_size = size

                return self._driver_pool

            self._driver_pool = DriverPool(size=size, timeout=self.timeout)
            self._driver_pool_size = size

            return self._driver_pool

    def _effective_cookie(self, cookie):
        return self.cookie if cookie is None else cookie

    def _analyze_url(self, url, cookie=None):
        self._check_open()

        if self.scan_type == "full":
            return self._analyze_full_url(url, self._effective_cookie(cookie))

        return url, http_scan(url, self.scan_type, self._effective_cookie(cookie))

    def _analyze_full_url(self, url, cookie=None):
        driver_pool = self._ensure_driver_pool(self._browser_worker_count())

        with driver_pool.get_driver() as driver:
            if cookie:
                for cookie_dict in cookie_to_cookies(cookie):
                    driver.add_cookie(cookie_dict)

            result_url, detections = process_url(driver, url)

        return result_url, merge_technologies(detections)


Scanner = Wappalyzer


def analyze(url, scan_type="full", workers=1, cookie=None, timeout=30):
    with Wappalyzer(
        scan_type=scan_type,
        workers=workers,
        cookie=cookie,
        timeout=timeout,
    ) as scanner:
        return scanner.analyze(url)
