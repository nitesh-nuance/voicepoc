#!/usr/bin/env python3
"""
Simple HTTP server to serve the ACS test client
Run this script and then open http://localhost:8000/test-client-local-server.html
"""
import http.server
import socketserver
import webbrowser
import os
import sys

# Configuration
PORT = 8000
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class CORSHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Simple HTTP request handler with CORS enabled"""
    
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

def main():
    # Change to the script directory
    os.chdir(DIRECTORY)
    
    print(f"🌐 Starting HTTP server on port {PORT}")
    print(f"📁 Serving files from: {DIRECTORY}")
    print(f"🔗 Open this URL in your browser:")
    print(f"   http://localhost:{PORT}/test-client-local-server.html")
    print(f"⏹️  Press Ctrl+C to stop the server")
    print("-" * 60)
    
    # Create server
    with socketserver.TCPServer(("", PORT), CORSHTTPRequestHandler) as httpd:
        try:
            # Optional: Auto-open browser
            if len(sys.argv) > 1 and sys.argv[1] == "--open":
                webbrowser.open(f"http://localhost:{PORT}/test-client-local-server.html")
            
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped by user")

if __name__ == "__main__":
    main()
