const http = require('http');

const body = JSON.stringify({
  service: 'greenlab-fixed',
  category: 'general-purpose',
  subject: 'node',
  payload: 'nodefixed'.repeat(1024),
});

const server = http.createServer((req, res) => {
  res.writeHead(200, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body),
  });
  res.end(body);
});

server.listen(8080, '0.0.0.0');
