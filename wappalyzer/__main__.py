import argparse
import queue
import re
import sys
import threading
import tldextract

from queue import Queue
from huepy import bold, green

from wappalyzer.core.analyzer import http_scan
from wappalyzer.core.utils import pretty_print, write_to_file
from wappalyzer.browser.analyzer import DriverPool, cookie_to_cookies, process_url, merge_technologies

def analyze(url, scan_type='full', workers=3, cookie=None, timeout=30):
    """Analyze a single URL"""
    if scan_type.lower() == 'full':
        driver_pool = None
        try:
            driver_pool = DriverPool(size=1, timeout=timeout)  # Single driver for one URL
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
                        print(f"Error during final cleanup: {str(e)}", file=sys.stderr)
    return {url: http_scan(url, scan_type, cookie)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', help='import from file or enter a url', dest='input_file')
    parser.add_argument('--scan-type', help='fast, balanced or full', dest='scan_type', default='full', type=str.lower)
    parser.add_argument('-w', '--workers', help='number of concurrent workers', dest='worker_num', default=5, type=int)
    parser.add_argument('-oJ', help='json output file, or stdout when omitted or set to -', dest='json_output_file', nargs='?', const='-')
    parser.add_argument('-oC', help='csv output file, or stdout when omitted or set to -', dest='csv_output_file', nargs='?', const='-')
    parser.add_argument('-oH', help='html output file, or stdout when omitted or set to -', dest='html_output_file', nargs='?', const='-')
    parser.add_argument('-c', '--cookie', help='cookie string', dest='cookie')
    parser.add_argument('-t', '--timeout', help='maximum seconds to wait for a page load in full scans', dest='timeout', default=30, type=int)
    args = parser.parse_args()

    print('\n\t' + bold(green('wappalyzer')) + '\n', file=sys.stderr)
    if not args.input_file:
        parser.print_help(file=sys.stderr)
        exit(22)
    
    def process_urls(urls, num_workers=3, cookie=None, scan_type='full', should_print=False, timeout=30):
        """Process multiple URLs using a driver pool"""
        results = {}
        driver_pool = None
        interrupted = False
        urls = [url for url in urls if url]

        if not urls:
            return results
        
        def worker(worker_id, url_queue, result_queue, lock, cookie, scan_type='full'):
            """Process URLs from the queue"""
            try:
                while not interrupted:
                    try:
                        url = url_queue.get_nowait()
                    except queue.Empty:
                        break

                    detections = None
                    try:
                        if scan_type == 'full':
                            with driver_pool.get_driver() as driver:
                                if cookie:
                                    for cookie_dict in cookie_to_cookies(cookie):
                                        driver.add_cookie(cookie_dict)
                                url, detections = process_url(driver, url)
                        else:
                            detections = http_scan(url, scan_type, cookie)
                    except Exception as e:
                        print(f"Error processing: {url}", file=sys.stderr)
                    finally:
                        with lock:
                            result_queue.put((url, detections))
                        url_queue.task_done()
            except Exception as e:
                print(f"Worker {worker_id} encountered an error: {str(e)}", file=sys.stderr)
        
        try:
            worker_count = min(num_workers, 3, len(urls)) if scan_type == 'full' else min(num_workers, len(urls))
            driver_pool = DriverPool(size=worker_count, timeout=timeout) if scan_type == 'full' else None  # Limit max concurrent drivers
            
            url_queue = Queue()
            result_queue = Queue()
            for url in urls:
                url_queue.put(url)
                
            threads = []
            lock = threading.Lock()
            
            for i in range(worker_count):
                thread = threading.Thread(
                    target=worker,
                    args=(i, url_queue, result_queue, lock, cookie, scan_type)
                )
                thread.start()
                threads.append(thread)

            def clear_status_line():
                if should_print:
                    print('\r\033[K', end='', file=sys.stderr, flush=True)

            def print_status(processed_count):
                if should_print:
                    print(
                        f'\r\033[KProcessed {processed_count}/{len(urls)} URLs',
                        end='',
                        file=sys.stderr,
                        flush=True,
                    )

            def print_finished_result(url, detections):
                if not detections:
                    return

                clear_status_line()
                if scan_type == 'full':
                    pretty_print({url: merge_technologies(detections)})
                else:
                    pretty_print({url: detections})

            processed_count = 0
            print_status(processed_count)

            try:
                while processed_count < len(urls):
                    try:
                        url, detections = result_queue.get(timeout=0.1)
                    except queue.Empty:
                        if all(not thread.is_alive() for thread in threads):
                            break
                        continue

                    processed_count += 1

                    if scan_type == 'full':
                        merged = merge_technologies(detections) if detections else {}
                        if merged:
                            results[url] = merged
                    else:
                        detections = detections or {}
                        results[url] = detections

                    if should_print:
                        print_finished_result(url, detections)
                        print_status(processed_count)

                    result_queue.task_done()
            except KeyboardInterrupt:
                interrupted = True
                if should_print:
                    clear_status_line()
                print("\nInterrupted! Saving partial results...", file=sys.stderr)

            for thread in threads:
                thread.join()

            while not result_queue.empty():
                url, detections = result_queue.get()
                processed_count += 1
                if scan_type == 'full':
                    merged = merge_technologies(detections) if detections else {}
                    if merged:
                        results[url] = merged
                else:
                    detections = detections or {}
                    results[url] = detections
                result_queue.task_done()

            if should_print:
                print_status(processed_count)
                sys.stderr.write('\n')
                sys.stderr.flush()
                    
            return results
            
        except Exception as e:
            print(f"Error in process_urls: {str(e)}", file=sys.stderr)
            return results
        finally:
            if driver_pool:
                try:
                    driver_pool.cleanup()
                except Exception as e:
                    print(f"Error during final cleanup: {str(e)}", file=sys.stderr)

    try:
        if re.search(r'^https?://', args.input_file.lower()):
            should_print = not (args.json_output_file or args.csv_output_file or args.html_output_file)
            result = analyze(args.input_file, args.scan_type, args.worker_num, args.cookie, args.timeout)
            if should_print:
                pretty_print(result)
        else:
            try:
                urls_file = open(args.input_file, 'r')
                urls = urls_file.read().splitlines()
                urls_file.close()
                should_print = not (args.json_output_file or args.csv_output_file or args.html_output_file)
                result = process_urls(urls, args.worker_num, args.cookie, args.scan_type, should_print=should_print, timeout=args.timeout)
            except FileNotFoundError:
                if tldextract.extract('http://' + args.input_file).domain != '':
                    should_print = not (args.json_output_file or args.csv_output_file or args.html_output_file)
                    result = analyze('http://' + args.input_file, args.scan_type, args.worker_num, args.cookie, args.timeout)
                    if should_print:
                        pretty_print(result)
                else:
                    print(
                        f"The argument '{args.input_file}' is neither a valid URL nor a file path.",
                        file=sys.stderr,
                    )
                    exit(22)

    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Saving partial results...", file=sys.stderr)
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
