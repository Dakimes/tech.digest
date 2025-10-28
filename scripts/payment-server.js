#!/usr/bin/env node
// Lightweight server for creating YooKassa payments and persisting orders locally.
// Run with: node scripts/payment-server.js

const http = require('node:http');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');

const PORT = process.env.PORT || 8787;
const SHOP_ID = process.env.YOOKASSA_SHOP_ID;
const SECRET_KEY = process.env.YOOKASSA_SECRET_KEY;
const RETURN_URL = process.env.YOOKASSA_RETURN_URL || 'https://example.com/thank-you';
const AMOUNT_VALUE = process.env.TECH_RADAR_PRICE || '1000.00';
const DESCRIPTION = process.env.TECH_RADAR_DESCRIPTION || 'Заказ технологического радара';
const VAT_CODE = Number(process.env.TECH_RADAR_VAT_CODE || 1);

const ordersFile = path.join(__dirname, '..', 'data', 'orders.json');

async function ensureOrdersFile(){
  try{
    await fs.mkdir(path.dirname(ordersFile), { recursive: true });
    await fs.access(ordersFile);
  } catch(err){
    await fs.writeFile(ordersFile, '[]', 'utf8');
  }
}

async function saveOrder(order){
  await ensureOrdersFile();
  const raw = await fs.readFile(ordersFile, 'utf8');
  const orders = raw ? JSON.parse(raw) : [];
  orders.push(order);
  await fs.writeFile(ordersFile, JSON.stringify(orders, null, 2), 'utf8');
}

async function createPayment({ email, phone }){
  if(!SHOP_ID || !SECRET_KEY){
    throw new Error('YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY должны быть заданы в переменных окружения.');
  }

  if(typeof fetch !== 'function'){
    throw new Error('Global fetch не найден. Используйте Node.js 18+ или добавьте полифилл fetch.');
  }

  const payload = {
    amount: {
      value: AMOUNT_VALUE,
      currency: 'RUB'
    },
    capture: true,
    description: DESCRIPTION,
    confirmation: {
      type: 'redirect',
      return_url: RETURN_URL
    },
    receipt: {
      customer: {
        email,
        phone
      },
      items: [
        {
          description: DESCRIPTION,
          quantity: '1',
          amount: {
            value: AMOUNT_VALUE,
            currency: 'RUB'
          },
          vat_code: VAT_CODE
        }
      ]
    }
  };

  const response = await fetch('https://api.yookassa.ru/v3/payments', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotence-Key': randomUUID(),
      Authorization: `Basic ${Buffer.from(`${SHOP_ID}:${SECRET_KEY}`).toString('base64')}`
    },
    body: JSON.stringify(payload)
  });

  if(!response.ok){
    const errorPayload = await response.json().catch(()=>({}));
    const details = errorPayload?.description || response.statusText;
    throw new Error(`YooKassa API error: ${details}`);
  }

  return response.json();
}

function sendJson(res, statusCode, data){
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type'
  });
  res.end(JSON.stringify(data));
}

const server = http.createServer(async (req, res) => {
  if(req.method === 'OPTIONS'){
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'POST, OPTIONS'
    });
    return res.end();
  }

  if(req.method !== 'POST' || req.url !== '/api/create-payment'){
    res.writeHead(404, { 'Content-Type': 'application/json; charset=utf-8' });
    return res.end(JSON.stringify({ message: 'Not Found' }));
  }

  try{
    const chunks = [];
    for await (const chunk of req){
      chunks.push(chunk);
    }

    const rawBody = Buffer.concat(chunks).toString('utf8');
    const payload = rawBody ? JSON.parse(rawBody) : {};
    const email = typeof payload.email === 'string' ? payload.email.trim() : '';
    const phone = typeof payload.phone === 'string' ? payload.phone.trim() : '';

    if(!email || !phone){
      return sendJson(res, 400, { message: 'Email и номер телефона обязательны.' });
    }

    const order = {
      email,
      phone,
      createdAt: new Date().toISOString()
    };

    await saveOrder(order);

    const payment = await createPayment(order);

    return sendJson(res, 200, {
      paymentId: payment?.id,
      confirmationUrl: payment?.confirmation?.confirmation_url
    });
  } catch(err){
    console.error('[payment-server]', err);
    return sendJson(res, 500, { message: err.message || 'Internal Server Error' });
  }
});

server.listen(PORT, () => {
  console.log(`Payment server listening on http://localhost:${PORT}`);
});
