import http.server
import socketserver
import json
import os
import smtplib
import traceback
import threading
from urllib.parse import urlparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

PORT = 8000
# Use absolute path for robustness
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')

print(f"Server starting...")
print(f"Base Directory: {BASE_DIR}")
print(f"Public Directory: {PUBLIC_DIR}")

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        try:
            if path == '/':
                path = '/index.html'
            
            if path == '/api/health':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))
                return

            # Serve static files from public directory
            # Remove leading slash to join correctly
            clean_path = path.lstrip('/')
            file_path = os.path.join(PUBLIC_DIR, clean_path)
            
            print(f"Request: {self.path} -> Mapped to: {file_path}")

            if os.path.exists(file_path) and os.path.isfile(file_path):
                # SimpleHTTPRequestHandler serves relative to current directory (which we will set to PUBLIC_DIR via translate_path or os.chdir)
                # But to be safe, we will just use translate_path to point to PUBLIC_DIR
                self.path = path
                return super().do_GET()
            else:
                print(f"File not found: {file_path}")
                self.send_error(404, f"File not found: {path}")
        except Exception as e:
            print(f"Error in do_GET: {e}")
            traceback.print_exc()
            self.send_error(500, str(e))

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == '/api/send':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                print(f"[{threading.current_thread().name}] Received send request")
                results = self.send_emails(data)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'success', 
                    'message': 'Email processing completed',
                    'results': results
                }).encode('utf-8'))
                
            except Exception as e:
                print(f"Error in do_POST: {e}")
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'status': 'error', 
                    'message': str(e)
                }).encode('utf-8'))
        else:
            self.send_error(404, "Endpoint not found")

    def send_emails(self, data):
        smtp_config = data.get('smtp_config')
        template = data.get('template')
        contacts = data.get('contacts')

        sender_email = smtp_config.get('email')
        password = smtp_config.get('password')
        host = smtp_config.get('host', 'smtp.gmail.com')
        port = int(smtp_config.get('port', 587))
        
        results = []

        try:
            print(f"Connecting to SMTP server {host}:{port}...")
            server = smtplib.SMTP(host, port, timeout=30) # 30s connection timeout
            server.set_debuglevel(1)
            server.ehlo()
            server.starttls()
            server.ehlo()
            print("Logging in...")
            server.login(sender_email, password)
            print("Login successful")

            for contact in contacts:
                contact_email = contact.get('email')
                try:
                    msg = MIMEMultipart()
                    msg['From'] = sender_email
                    msg['To'] = contact_email
                    
                    # Personalize subject and body
                    subject = template.get('subject')
                    body = template.get('body')
                    
                    for key, value in contact.items():
                        placeholder = f"{{{{{key}}}}}"
                        subject = subject.replace(placeholder, str(value))
                        body = body.replace(placeholder, str(value))
                    
                    msg['Subject'] = subject
                    msg.attach(MIMEText(body, 'plain'))
                    
                    server.send_message(msg)
                    print(f"Sent to {contact_email}")
                    results.append({'email': contact_email, 'status': 'sent'})
                except Exception as e:
                    print(f"Failed to send to {contact_email}: {e}")
                    results.append({'email': contact_email, 'status': 'failed', 'error': str(e)})

            server.quit()
            return results
        except smtplib.SMTPAuthenticationError as e:
            print(f"Authentication Error: {e}")
            raise Exception("Authentication failed. Please check your email and App Password.")
        except Exception as e:
            print(f"SMTP Error: {e}")
            raise e

    def translate_path(self, path):
        # Override to serve from PUBLIC_DIR
        # Ensure we strip query params here too just in case, though do_GET handles it
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        words = path.split('/')
        words = filter(None, words)
        path = PUBLIC_DIR
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                continue
            path = os.path.join(path, word)
        return path

if __name__ == '__main__':
    print(f"Starting Threaded Server at port {PORT}")
    
    with ThreadedTCPServer(("", PORT), CustomHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.server_close()
