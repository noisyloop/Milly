"""Tiny stand-in for the Ollama API, used only to record the README demo.

Streams canned replies word-by-word so the recording looks like a real
local model without needing Ollama or a GPU.
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPLIES = [
    ("coffee or tea",
     "Depends on the mood! Coffee for a quick, bold kick in the morning; "
     "tea when you want something gentler to sip through the afternoon."),
    ("cold brew",
     "Coarse-ground coffee steeped in cold water for 12-18 hours. It comes "
     "out smooth, low in acidity, and naturally a little sweet. Try 1 part "
     "coffee to 8 parts water, then dilute to taste."),
    ("green tea",
     "Use water around 75-80 C, not boiling, and steep for 2-3 minutes. "
     "Hotter water or longer steeping pulls out the bitter tannins."),
]
DEFAULT = "Hey! I'm Milly, running locally on this machine. What's on your mind?"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._json({"models": [{"model": m, "name": m} for m in
                               ("llama3.2:latest", "qwen3:8b", "gemma3:1b")]})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["content-length"])))
        # With RAG on, retrieved docs come first and the question follows "User: ".
        last = req["messages"][-1]["content"].rsplit("User: ", 1)[-1].lower()
        text = next((r for k, r in REPLIES if k in last), DEFAULT)
        self.send_response(200)
        self.send_header("content-type", "application/x-ndjson")
        self.end_headers()
        time.sleep(0.5)
        words = text.split(" ")
        for i, w in enumerate(words):
            msg = {"role": "assistant", "content": w + (" " if i < len(words) - 1 else "")}
            self.wfile.write((json.dumps({"model": req["model"], "created_at": "2026-01-01T00:00:00Z",
                                          "message": msg, "done": False}) + "\n").encode())
            self.wfile.flush()
            time.sleep(0.07)
        self.wfile.write((json.dumps({"model": req["model"], "created_at": "2026-01-01T00:00:00Z",
                                      "message": {"role": "assistant", "content": ""}, "done": True}) + "\n").encode())


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 11999), H).serve_forever()
