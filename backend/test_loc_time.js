const WebSocket = require('ws');

const ws = new WebSocket('ws://localhost:5000');
let locStart;

ws.on('open', () => {
  console.log('Connected to server');
});

ws.on('message', (data) => {
  const msg = JSON.parse(data.toString());
  
  if (msg.type === 'connected') {
    ws.send(JSON.stringify({ action: 'initialize' }));
  } else if (msg.action === 'statusUpdate' && msg.step === 'initialize' && msg.status === 'completed') {
    locStart = Date.now();
    console.log('Triggering setLocation...');
    ws.send(JSON.stringify({ action: 'setLocation', location: 'SUPERTECH ECO VILLAGE-1' }));
  } else if (msg.action === 'statusUpdate' && msg.step === 'setLocation') {
    if (msg.status === 'loading') {
      console.log(`[setLocation] Starting...`);
    } else if (msg.status === 'completed') {
      const elapsed = Date.now() - locStart;
      console.log(`[setLocation] DONE in ${elapsed}ms! message: ${msg.message}`);
      ws.close();
    } else if (msg.status === 'error') {
      const elapsed = Date.now() - locStart;
      console.log(`[setLocation] ERROR after ${elapsed}ms: ${msg.message}`);
      ws.close();
    }
  }
});

ws.on('error', (err) => console.error('WebSocket error:', err));
ws.on('close', () => console.log('Disconnected.'));
