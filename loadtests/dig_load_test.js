import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const digLatency = new Trend('dig_latency');
const digCounter = new Counter('digs_total');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 10 },   // Ramp up to 10 users
    { duration: '1m', target: 50 },    // Ramp up to 50 users
    { duration: '2m', target: 100 },   // Ramp up to 100 users
    { duration: '3m', target: 100 },   // Stay at 100 users
    { duration: '1m', target: 50 },    // Ramp down to 50 users
    { duration: '30s', target: 0 },    // Ramp down to 0
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% of requests under 500ms
    http_req_failed: ['rate<0.01'],    // Error rate under 1%
    errors: ['rate<0.05'],             // Custom error rate under 5%
  },
};

// Base URL - configure via environment variable
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const BOT_TOKEN = __ENV.BOT_TOKEN || '';
const WEBHOOK_URL = __ENV.WEBHOOK_URL || '';

// Simulated user data
const USERS = Array.from({ length: 1000 }, (_, i) => ({
  id: 1000000 + i,
  username: `testuser${i}`,
}));

export function setup() {
  // Verify health endpoint
  const res = http.get(`${BASE_URL}/health`);
  check(res, { 'health check ok': (r) => r.status === 200 });
  
  return { baseUrl: BASE_URL };
}

export default function (data) {
  const user = USERS[Math.floor(Math.random() * USERS.length)];
  const userId = user.id;
  const username = user.username;

  // Test health endpoint
  let res = http.get(`${data.baseUrl}/health`);
  check(res, { 'health status 200': (r) => r.status === 200 });
  errorRate.add(res.status !== 200);

  // Test metrics endpoint
  res = http.get(`${data.baseUrl}/metrics`);
  check(res, { 'metrics status 200': (r) => r.status === 200 });
  errorRate.add(res.status !== 200);

  // Test readiness endpoint
  res = http.get(`${data.baseUrl}/ready`);
  check(res, { 'ready status 200': (r) => r.status === 200 });
  errorRate.add(res.status !== 200);

  // Simulate dig command via webhook (if configured)
  if (WEBHOOK_URL) {
    const payload = JSON.stringify({
      update_id: Date.now(),
      message: {
        message_id: Date.now(),
        from: {
          id: userId,
          is_bot: false,
          first_name: 'Test',
          username: username,
        },
        chat: {
          id: userId,
          type: 'private',
        },
        date: Math.floor(Date.now() / 1000),
        text: '/dig',
      },
    });

    const startTime = Date.now();
    res = http.post(WEBHOOK_URL, payload, {
      headers: {
        'Content-Type': 'application/json',
        'X-Telegram-Bot-Api-Secret-Token': __ENV.WEBHOOK_SECRET || '',
      },
    });
    const latency = Date.now() - startTime;

    digLatency.add(latency);
    digCounter.add(1);

    const success = check(res, {
      'webhook status 200': (r) => r.status === 200,
      'webhook response ok': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.ok === true;
        } catch {
          return false;
        }
      },
    });

    errorRate.add(!success);
  }

  // Test API endpoints (if auth is available)
  // Note: In real test, you'd need valid Telegram initData
  // res = http.get(`${data.baseUrl}/api/v1/user/stats`, {
  //   headers: { 'X-Telegram-Init-Data': '...' },
  // });

  sleep(Math.random() * 2 + 1); // 1-3 seconds between requests
}

export function teardown(data) {
  // Cleanup if needed
  console.log('Load test completed');
}