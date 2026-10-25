/**
 * FARQ - WhatsApp Intake Engine for Deepfake Detection
 * Main Entry Point
 */
const { startDashboard } = require('./src/dashboard');
const { connectToWhatsApp } = require('./src/whatsapp');

console.log('Initializing FARQ WhatsApp Intake Engine...');

// 1. Launch local dashboard and /jobs API
startDashboard();

// 2. Connect to WhatsApp via Baileys WebSocket protocol
connectToWhatsApp();
