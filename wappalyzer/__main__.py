import argparse
import queue
import re
import sys
import threading
import tldextract

from queue import Queue
from huepy import bold, green

from wappalyzer.core.requester import get_response
from wappalyzer.core.analyzer import http_scan
from wappalyzer.core.utils import pretty_print, write_to_file
from wappalyzer.browser.analyzer import DriverPool, cookie_to_cookies, process_url, merge_technologies

def analyze(url, scan_type='full', threads=3, cookie=None):
    """Analyze a single URL"""
    if scan_type.lower() == 'full':
        driver_pool = None
        try:
            driver_pool = DriverPool(size=1)  # Single driver for one URL
            with driver_pool.get_driver() as driver:
                if cookie:
                    for cookie_dict in cookie_to_cookies(cookie):
                        driver.add_cookie(cookie_dict)
                url, detections = process_url(driver, url)
                return {url: merge_technologies(detections)}
        finally:
            if driver_pool:
                try:
                    driver_pool.cleanup()
                except Exception as e:
                    print(f"Error during final cleanup: {str(e)}")
    return {url: http_scan(url, scan_type, cookie)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', help='import from file or enter a url', dest='input_file')
    parser.add_argument('--scan-type', help='fast, balanced or full', dest='scan_type', default='full', type=str.lower)
    parser.add_argument('-t', '--threads', help='number of threads', dest='thread_num', default=5, type=int)
    parser.add_argument('-oJ', help='json output file', dest='json_output_file')
    parser.add_argument('-oC', help='csv output file', dest='csv_output_file')
    parser.add_argument('-oH', help='html output file', dest='html_output_file')
    parser.add_argument('-c', '--cookie', help='cookie string', dest='cookie')
    args = parser.parse_args()

    print('\n\t' + bold(green('wappalyzer')) + '\n')
    if not args.input_file:
        parser.print_help()
        exit(22)
    
    result_db = {}

    def process_detections(url_detections, scan_type='full'):
        result = {}
        for url, detections in url_detections:
            if scan_type == 'full':
                result[url] = merge_technologies(detections)
            else:
                result[url] = detections
        return result

    def process_urls(urls, num_threads=3, cookie=None, scan_type='full', should_print=False):
        """Process multiple URLs using a driver pool"""
        results = {}
        driver_pool = None
        interrupted = False
        
        def worker(worker_id, url_queue, result_queue, lock, cookie, scan_type='full'):
            """Process URLs from the queue"""
            try:
                while not interrupted:
                    try:
                        url = url_queue.get_nowait()
                    except queue.Empty:
                        break
                    
                    print(f"Processing: {url}")
                    try:
                        if scan_type == 'full':
                            with driver_pool.get_driver() as driver:
                                if cookie:
                                    for cookie_dict in cookie_to_cookies(cookie):
                                        driver.add_cookie(cookie_dict)
                                url, detections = process_url(driver, url)
                                if detections:
                                    with lock:
                                        result_queue.put((url, detections))
                        else:
                            detections = http_scan(url, scan_type, cookie)
                            with lock:
                                result_queue.put((url, detections))
                    except Exception as e:
                        print(f"Error processing: {url}")
                    finally:
                        url_queue.task_done()
            except Exception as e:
                print(f"Worker {worker_id} encountered an error: {str(e)}")
        
        try:
            driver_pool = DriverPool(size=min(num_threads, 3)) if scan_type == 'full' else None  # Limit max concurrent drivers
            
            url_queue = Queue()
            result_queue = Queue()
            for url in urls:
                url_queue.put(url)
                
            threads = []
            lock = threading.Lock()
            
            for i in range(num_threads):
                thread = threading.Thread(
                    target=worker,
                    args=(i, url_queue, result_queue, lock, cookie, scan_type)
                )
                thread.daemon = True
                thread.start()
                threads.append(thread)
                
            # Wait for all tasks to complete or interruption
            try:
                url_queue.join()
            except KeyboardInterrupt:
                interrupted = True
                print("\nInterrupted! Saving partial results...")
            
            # Process available results
            while not result_queue.empty():
                url, detections = result_queue.get()
                if should_print:
                    if scan_type == 'full':
                        pretty_print({url: merge_technologies(detections)})
                    else:
                        pretty_print({url: detections})
                if scan_type == 'full':
                    results[url] = merge_technologies(detections)
                else:
                    results[url] = detections
                    
            return results
            
        except Exception as e:
            print(f"Error in process_urls: {str(e)}")
            return results
        finally:
            if driver_pool:
                try:
                    driver_pool.cleanup()
                except Exception as e:
                    print(f"Error during final cleanup: {str(e)}")
                    # Try forceful cleanup if regular cleanup fails
                    try:
                        import psutil
                        for proc in psutil.process_iter(['name']):
                            if 'firefox' in proc.info['name'].lower():
                                proc.kill()
                    except Exception:
                        pass

    try:
        if re.search(r'^https?://', args.input_file.lower()):
            should_print = not (args.json_output_file or args.csv_output_file or args.html_output_file)
            result = analyze(args.input_file, args.scan_type, args.thread_num, args.cookie)
            if should_print:
                pretty_print(result)
        else:
            try:
                urls_file = open(args.input_file, 'r')
                urls = urls_file.read().splitlines()
                urls_file.close()
                should_print = not (args.json_output_file or args.csv_output_file or args.html_output_file)
                result = process_urls(urls, args.thread_num, args.cookie, args.scan_type, should_print=should_print)
            except FileNotFoundError:
                if tldextract.extract('http://' + args.input_file).domain != '':
                    should_print = not (args.json_output_file or args.csv_output_file or args.html_output_file)
                    result = analyze('http://' + args.input_file, args.scan_type, args.thread_num, args.cookie)
                    if should_print:
                        pretty_print(result)
                else:
                    print(f"The argument '{args.input_file}' is neither a valid URL nor a file path.")
                    exit(22)

    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Saving partial results...")
        pass

    if 'result' in locals():
        if args.json_output_file:
            write_to_file(args.json_output_file, result, format='json')
        elif args.csv_output_file:
            write_to_file(args.csv_output_file, result, format='csv')
        elif args.html_output_file:
            write_to_file(args.html_output_file, result, format='html')

if __name__ == '__main__':
    main()
