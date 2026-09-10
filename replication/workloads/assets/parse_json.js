const crypto = require('crypto');

const PAYLOAD = JSON.stringify({
  name: 'greenlab',
  vals: Array.from({length: 128}, (_, i) => i),
  nested: {k: 'v'.repeat(64), n: Array.from({length: 64}, (_, i) => i * i)},
});

function canonical(o) {
  if (o === null || typeof o !== 'object') return JSON.stringify(o);
  if (Array.isArray(o)) return '[' + o.map(canonical).join(',') + ']';
  const keys = Object.keys(o).sort();
  return '{' + keys.map(k => JSON.stringify(k) + ':' + canonical(o[k])).join(',') + '}';
}

const n = parseInt(process.argv[2], 10);
const h = crypto.createHash('sha256');
{
  const obj = JSON.parse(PAYLOAD);
  const c = canonical(obj);
  h.update(c);
  console.log(`COLD ${crypto.createHash('sha256').update(c).digest('hex')}`);
}
for (let i = 1; i < n; i++) {
  const obj = JSON.parse(PAYLOAD);
  h.update(canonical(obj));
}
console.log(`STEADY ${h.digest('hex')}`);
