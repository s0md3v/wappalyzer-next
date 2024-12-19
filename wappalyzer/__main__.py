import argparse
import queue
import re
import threading

from wappalyzer.core.requester import get_response
from wappalyzer.core.analyzer import http_scan
from wappalyzer.core.utils import pretty_print, write_to_file
from wappalyzer.browser.analyzer import init_firefox_driver, cookie_to_cookies, process_url, merge_technologies

parser = argparse.ArgumentParser()
parser.add_argument('-i', help='import from file or enter a url', dest='input_file')
parser.add_argument('--scan-type', help='fast, balanced or full', dest='scan_type', default='full', type=str.lower)
parser.add_argument('-t', '--threads', help='number of threads', dest='thread_num', default=5)
parser.add_argument('-oJ', help='json output file', dest='json_output_file')
parser.add_argument('-oC', help='csv output file', dest='csv_output_file')
parser.add_argument('-c', '--cookie', help='cookie string', dest='cookie')
args = parser.parse_args()

def analyze(url, scan_type='full', threads=3, cookie=None):
    if args.scan_type.lower() == 'full':
        cookies = cookie_to_cookies(cookie) if cookie else []
        driver = init_firefox_driver(cookies)
        url, detections = process_url(driver, url)
        driver.quit()
        return {url: merge_technologies(detections)}
    return {url: http_scan(url, scan_type, cookie)}

def main():
    result_db = {}
    def worker(worker_id, url_queue, result_queue, lock, cookie, scan_type='full'):
        driver = None
        try:
            while True:
                try:
                    url = url_queue.get_nowait()
                except queue.Empty:
                    break
                print(f"Worker {worker_id}: Processing {url}")
                detections = []
                if scan_type == 'full':
                    cookies = cookie_to_cookies(cookie) if cookie else []
                    driver = init_firefox_driver(cookies)
                    url, detections = process_url(driver, url)
                else:
                    detections = http_scan(url, scan_type, cookie)
                if detections:
                    with lock:
                        result_queue.put((url, detections))
                else:
                    pass
                url_queue.task_done()
        finally:
            if scan_type == 'full' and driver:
                driver.quit()

    def process_detections(url_detections, scan_type='full'):
        result = {}
        for url, detections in url_detections:
            if scan_type == 'full':
                result[url] = merge_technologies(detections)
            else:
                result[url] = detections
        return result

    def process_urls(urls, threads, cookie, scan_type='full', print=False):
        """Process multiple URLs in parallel and return results grouped by URL"""
        url_queue = queue.Queue()
        result_queue = queue.Queue()
        lock = threading.Lock()
        
        for url in urls:
            url_queue.put(url)
        
        threads_store = []
        for i in range(threads):
            thread = threading.Thread(
                target=worker,
                args=(i, url_queue, result_queue, lock, cookie, scan_type)
            )
            thread.start()
            threads_store.append(thread)
        
        for thread in threads_store:
            thread.join()
        
        url_detections = []
        while not result_queue.empty():
            this_result = result_queue.get()
            if print:
                pretty_print(process_detections([this_result], scan_type=scan_type))
            url_detections.append(this_result)
        
        return process_detections(url_detections, scan_type)

    if re.search(r'^https?://', args.input_file.lower()):
        result = analyze(args.input_file, args.scan_type, args.thread_num, args.cookie)
        if args.json_output_file:
            write_to_file(args.json_output_file, result, format='json')
        elif args.csv_output_file:
            write_to_file(args.csv_output_file, result, format='csv')
        else:
            pretty_print(result)
    else:
        urls_file = open(args.input_file, 'r')
        urls = urls_file.read().splitlines()
        urls_file.close()
        should_print = True if not args.json_output_file and not args.csv_output_file else False
        results = process_urls(urls, args.thread_num, args.cookie, args.scan_type, print=should_print)
        if args.json_output_file:
            write_to_file(args.json_output_file, results, format='json')
        elif args.csv_output_file:
            write_to_file(args.csv_output_file, results, format='csv')

if __name__ == '__main__':
    main()