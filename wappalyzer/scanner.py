import asyncio
import concurrent.futures
import threading

from wappalyzer.browser.analyzer import (
    DriverPool,
    cookie_to_cookies,
    merge_technologies,
    process_url,
)
from wappalyzer.core.analyzer import http_scan


class _LoopRunner:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)

        try:
            return future.result()
        except KeyboardInterrupt:
            future.cancel()
            raise

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()


class _FullScanBackend:
    MAX_BROWSER_WORKERS = 3

    def __init__(self, workers=1, timeout=30):
        self.workers = workers
        self.timeout = timeout
        self.pool = None
        self.pool_size = 0

    async def ensure_pool(self, size):
        if self.pool:
            if size > self.pool_size:
                await self.pool.grow_to(size)
                self.pool_size = size

            return

        pool = DriverPool(size=size, timeout=self.timeout)

        try:
            await pool.start()
        except Exception:
            await pool.cleanup()
            raise

        self.pool = pool
        self.pool_size = size

    async def analyze_url(self, url, cookie=None):
        await self.ensure_pool(1)

        async with self.pool.get_driver() as driver:
            if cookie:
                for cookie_dict in cookie_to_cookies(cookie):
                    driver.add_cookie(cookie_dict)

            result_url, detections = await process_url(driver, url)

        return result_url, merge_technologies(detections)

    async def analyze_many(self, urls, cookie=None, on_result=None, on_error=None):
        urls = [url for url in urls if url]

        if not urls:
            return {}

        worker_count = min(self.workers, self.MAX_BROWSER_WORKERS, len(urls))
        await self.ensure_pool(worker_count)

        queue = asyncio.Queue()
        results = {}

        for url in urls:
            queue.put_nowait(url)

        async def worker():
            while True:
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                result_url = url
                technologies = {}
                error = None

                try:
                    result_url, technologies = await self.analyze_url(url, cookie)
                except Exception as exc:
                    error = exc

                results[result_url] = technologies

                if error and on_error:
                    on_error(result_url, error)

                if on_result:
                    on_result(result_url, technologies)

                queue.task_done()

        workers = [
            asyncio.create_task(worker())
            for _ in range(worker_count)
        ]

        try:
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            for worker_task in workers:
                worker_task.cancel()

            raise

        return results

    async def close(self):
        if self.pool:
            await self.pool.cleanup()
            self.pool = None
            self.pool_size = 0


class Wappalyzer:
    SUPPORTED_SCAN_TYPES = {"fast", "balanced", "full"}

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
        self._closed = False
        self._runner = None
        self._full_backend = None
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
            runner = self._runner
            backend = self._full_backend
            self._runner = None
            self._full_backend = None

        if runner and backend:
            try:
                runner.run(backend.close())
            finally:
                runner.close()
        elif runner:
            runner.close()

    def analyze(self, url, cookie=None):
        result_url, technologies = self._analyze_url(url, cookie)

        return {result_url: technologies}

    def analyze_many(self, urls, cookie=None, on_result=None, on_error=None):
        urls = [url for url in urls if url]

        if not urls:
            return {}

        self._check_open()

        if self.scan_type == "full":
            return self._full_runner().run(
                self._full_backend.analyze_many(
                    urls,
                    cookie=self._effective_cookie(cookie),
                    on_result=on_result,
                    on_error=on_error,
                )
            )

        return self._analyze_many_http(
            urls,
            cookie=self._effective_cookie(cookie),
            on_result=on_result,
            on_error=on_error,
        )

    def _check_open(self):
        if self._closed:
            raise RuntimeError("Wappalyzer scanner is closed")

    def _effective_cookie(self, cookie):
        return self.cookie if cookie is None else cookie

    def _full_runner(self):
        with self._lock:
            self._check_open()

            if not self._runner:
                self._runner = _LoopRunner()
                self._full_backend = _FullScanBackend(
                    workers=self.workers,
                    timeout=self.timeout,
                )

            return self._runner

    def _analyze_url(self, url, cookie=None):
        self._check_open()
        cookie = self._effective_cookie(cookie)

        if self.scan_type == "full":
            return self._full_runner().run(
                self._full_backend.analyze_url(url, cookie=cookie)
            )

        return url, http_scan(url, self.scan_type, cookie)

    def _analyze_many_http(self, urls, cookie=None, on_result=None, on_error=None):
        worker_count = min(self.workers, len(urls))
        results = {}

        def scan(url):
            return url, http_scan(url, self.scan_type, cookie)

        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_url = {
                executor.submit(scan, url): url
                for url in urls
            }

            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                result_url = url
                technologies = {}
                error = None

                try:
                    result_url, technologies = future.result()
                except Exception as exc:
                    error = exc

                results[result_url] = technologies

                if error and on_error:
                    on_error(result_url, error)

                if on_result:
                    on_result(result_url, technologies)

        return results


Scanner = Wappalyzer


def analyze(url, scan_type="full", workers=1, cookie=None, timeout=30):
    with Wappalyzer(
        scan_type=scan_type,
        workers=workers,
        cookie=cookie,
        timeout=timeout,
    ) as scanner:
        return scanner.analyze(url)
