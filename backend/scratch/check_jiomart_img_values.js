const WebSocket = require('ws');

const ws = new WebSocket('ws://localhost:5000');
let locStart;

ws.on('open', () => {
  ws.send(JSON.stringify({ action: 'initialize' }));
});

ws.on('message', (data) => {
  const msg = JSON.parse(data.toString());

  if (msg.action === 'statusUpdate' && msg.step === 'initialize' && msg.status === 'completed') {
    locStart = Date.now();
    ws.send(JSON.stringify({ action: 'setLocation', location: '201306' }));
  } else if (msg.action === 'statusUpdate' && msg.step === 'setLocation' && msg.status === 'completed') {
    ws.send(JSON.stringify({ action: 'search', query: 'almond' }));
  } else if (msg.action === 'searchResult' && msg.service === 'jiomart') {
    console.log('JioMart products list:');
    const firstProducts = msg.data.slice(0, 5);
    firstProducts.forEach(p => {
      console.log(`- ${p.name}: ${p.imageUrl ? p.imageUrl.slice(0, 100) : 'NO IMAGE URL'}`);
    });
    ws.close();
  }
});

ws.on('error', err => console.error(err));
