import socket
import threading
import http.server
import urllib.request
import socks
import cachetools
import hashlib
import os

# Настройки SOCKS-прокси
SOCKS_PROXY_HOST = 'localhost'
SOCKS_PROXY_PORT = 9050

# Настройки HTTP-прокси
HTTP_PROXY_HOST = 'localhost'
HTTP_PROXY_PORT = 8080

# Устанавливаем SOCKS-прокси
socks.set_default_proxy(socks.SOCKS5, SOCKS_PROXY_HOST, SOCKS_PROXY_PORT)
socket.socket = socks.socksocket

# Настройки кэша
CACHE_SIZE = 100  # Количество элементов в кэше
cache = cachetools.LRUCache(maxsize=CACHE_SIZE)

# Расширения статических файлов
STATIC_EXTENSIONS = ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf', '.eot']

def get_cache_key(url, headers, method):
    key = method + url + str(headers)
    return hashlib.md5(key.encode()).hexdigest()

def is_static_file(url):
    _, ext = os.path.splitext(url)
    return ext in STATIC_EXTENSIONS

class ProxyHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.proxy_request()

    def do_POST(self):
        self.proxy_request()

    def do_CONNECT(self):
        self.proxy_connect()

    def proxy_request(self):
        try:
            url = self.path
            cache_key = get_cache_key(url, self.headers, self.command)
            
            if is_static_file(url) and cache_key in cache:
                print(f'Cache hit for: {url}')
                cached_response = cache[cache_key]
                self.send_response(cached_response['status'])
                for header, value in cached_response['headers'].items():
                    self.send_header(header, value)
                self.end_headers()
                self.wfile.write(cached_response['content'])
                return

            print(f'Proxying request for: {url}')
            req = urllib.request.Request(url)
            req.method = self.command
            req.headers = self.headers

            content_length = self.headers.get('Content-Length')
            if content_length:
                length = int(content_length)
                req.data = self.rfile.read(length)

            with urllib.request.urlopen(req) as response:
                response_content = response.read()
                self.send_response(response.status)
                response_headers = {header: value for header, value in response.getheaders()}
                for header, value in response_headers.items():
                    self.send_header(header, value)
                self.end_headers()
                self.wfile.write(response_content)

                if is_static_file(url):
                    cache[cache_key] = {
                        'status': response.status,
                        'headers': response_headers,
                        'content': response_content
                    }
        except Exception as e:
            self.send_error(500, str(e))

    def proxy_connect(self):
        try:
            host, port = self.path.split(':')
            port = int(port)

            print(f'Connecting to {host}:{port}')

            with socks.socksocket() as sock:
                sock.connect((host, port))
                self.send_response(200, 'Connection established')
                self.end_headers()

                self.connection.setblocking(False)
                sock.setblocking(False)

                while True:
                    try:
                        data = self.connection.recv(8192)
                        if data:
                            sock.sendall(data)
                        else:
                            break
                    except BlockingIOError:
                        pass

                    try:
                        data = sock.recv(8192)
                        if data:
                            self.connection.sendall(data)
                        else:
                            break
                    except BlockingIOError:
                        pass
        except Exception as e:
            self.send_error(500, str(e))

def run_server():
    server_address = (HTTP_PROXY_HOST, HTTP_PROXY_PORT)
    httpd = http.server.HTTPServer(server_address, ProxyHTTPRequestHandler)
    print(f'HTTP to SOCKS proxy server running on {HTTP_PROXY_HOST}:{HTTP_PROXY_PORT}')
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
