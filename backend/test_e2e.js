const WebSocket = require('ws');

const ws = new WebSocket('ws://localhost:5000');
let phase = 'init';
let locStart, searchStart;

ws.on('open', () => console.log('Connected'));

ws.on('message', (data) => {
  const msg = JSON.parse(data.toString());

  if (msg.type === 'connected') {
    ws.send(JSON.stringify({ action: 'initialize' }));

  } else if (msg.action === 'statusUpdate' && msg.step === 'initialize' && msg.status === 'completed') {
    locStart = Date.now();
    ws.send(JSON.stringify({ action: 'setLocation', location: '201306' }));

  } else if (msg.action === 'statusUpdate' && msg.step === 'setLocation') {
    if (msg.status === 'completed') {
      console.log(`[setLocation] DONE in ${Date.now() - locStart}ms`);
      searchStart = Date.now();
      ws.send(JSON.stringify({ action: 'search', query: 'milk' }));
    } else if (msg.status === 'error') {
      console.log(`[setLocation] ERROR: ${msg.message}`);
      ws.close();
    }

  } else if (msg.action === 'searchResult') {
    console.log(`[searchResult] ${msg.service}: ${msg.data?.length ?? 0} products`);

  } else if (msg.action === 'statusUpdate' && msg.step === 'search') {
    if (msg.status === 'completed') {
      console.log(`[search] ALL DONE in ${Date.now() - searchStart}ms. Total: ${Date.now() - locStart}ms`);
      ws.close();
    } else if (msg.status === 'error') {
      console.log(`[search] ERROR: ${msg.message}`);
      ws.close();
    }
  }
});

ws.on('error', err => console.error('WS error:', err.message));
ws.on('close', () => console.log('Done.'));
