import argparse
import re
import sys

import tldextract
from huepy import bold, green

from wappalyzer.core.utils import pretty_print, write_to_file
from wappalyzer.scanner import Wappalyzer, analyze


def positive_int(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer")

    if number < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")

    return number


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', help='import from file or enter a url', dest='input_file')
    parser.add_argument('--scan-type', help='fast, balanced or full', dest='scan_type', default='full', type=str.lower, choices=('fast', 'balanced', 'full'))
    parser.add_argument('-w', '--workers', help='number of concurrent workers', dest='worker_num', default=5, type=positive_int)
    parser.add_argument('-oJ', help='json output file, or stdout when omitted or set to -', dest='json_output_file', nargs='?', const='-')
    parser.add_argument('-oC', help='csv output file, or stdout when omitted or set to -', dest='csv_output_file', nargs='?', const='-')
    parser.add_argument('-oH', help='html output file, or stdout when omitted or set to -', dest='html_output_file', nargs='?', const='-')
    parser.add_argument('-c', '--cookie', help='cookie string', dest='cookie')
    parser.add_argument('-t', '--timeout', help='maximum seconds to wait for a page load in full scans', dest='timeout', default=30, type=positive_int)
    args = parser.parse_args()

    print('\n\t' + bold(green('wappalyzer')) + '\n', file=sys.stderr)

    if not args.input_file:
        parser.print_help(file=sys.stderr)
        exit(22)

    def has_file_output():
        return bool(args.json_output_file or args.csv_output_file or args.html_output_file)

    def process_urls(urls, num_workers=3, cookie=None, scan_type='full', should_print=False, timeout=30):
        urls = [url for url in urls if url]

        if not urls:
            return {}

        results = {}
        processed_count = 0
        status_enabled = True

        def clear_status_line():
            if status_enabled:
                print('\r\033[K', end='', file=sys.stderr, flush=True)

        def print_status():
            if status_enabled:
                print(
                    f'\r\033[KProcessed {processed_count}/{len(urls)} URLs',
                    end='',
                    file=sys.stderr,
                    flush=True,
                )

        def handle_error(url, error):
            clear_status_line()
            print(f"Error processing: {url}: {error}", file=sys.stderr)

        def handle_result(url, technologies):
            nonlocal processed_count

            processed_count += 1
            results[url] = technologies

            if should_print and technologies:
                clear_status_line()
                pretty_print({url: technologies})

            print_status()

        try:
            with Wappalyzer(
                scan_type=scan_type,
                workers=num_workers,
                cookie=cookie,
                timeout=timeout,
            ) as scanner:
                print_status()
                scanner_results = scanner.analyze_many(
                    urls,
                    on_result=handle_result,
                    on_error=handle_error,
                )
                results.update(scanner_results)
        except KeyboardInterrupt:
            clear_status_line()
            print("\nInterrupted! Saving partial results...", file=sys.stderr)
        except Exception as e:
            clear_status_line()
            print(f"Error in process_urls: {str(e)}", file=sys.stderr)
        finally:
            if status_enabled:
                sys.stderr.write('\n')
                sys.stderr.flush()

        return results

    try:
        if re.search(r'^https?://', args.input_file.lower()):
            should_print = not has_file_output()
            result = analyze(
                args.input_file,
                args.scan_type,
                1,
                args.cookie,
                args.timeout,
            )
            if should_print:
                pretty_print(result)
        else:
            try:
                with open(args.input_file, 'r') as urls_file:
                    urls = urls_file.read().splitlines()

                should_print = not has_file_output()
                result = process_urls(
                    urls,
                    args.worker_num,
                    args.cookie,
                    args.scan_type,
                    should_print=should_print,
                    timeout=args.timeout,
                )
            except FileNotFoundError:
                if tldextract.extract('http://' + args.input_file).domain != '':
                    should_print = not has_file_output()
                    result = analyze(
                        'http://' + args.input_file,
                        args.scan_type,
                        1,
                        args.cookie,
                        args.timeout,
                    )
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

    if 'result' in locals():
        if args.json_output_file:
            write_to_file(args.json_output_file, result, format='json')
        elif args.csv_output_file:
            write_to_file(args.csv_output_file, result, format='csv')
        elif args.html_output_file:
            write_to_file(args.html_output_file, result, format='html')


if __name__ == '__main__':
    main()
