import api from './axiosInstance';

// ── Chat endpoints ────────────────────────────────────────────────────

export const getWhatsAppChats = () =>
  api.get('/whatsapp/chats').then((r) => r.data);

export const getChatMessages = (leadId) =>
  api.get(`/whatsapp/chats/${leadId}`).then((r) => r.data);

export const sendWhatsAppMessage = (leadId, content) =>
  api.post(`/whatsapp/chats/${leadId}/send`, { content }).then((r) => r.data);

export const deleteWhatsAppChat = (leadId) =>
  api.delete(`/whatsapp/chats/${leadId}`).then((r) => r.data);

// ── Instance management ───────────────────────────────────────────────

export const createWhatsAppInstance = (instanceName) =>
  api.post('/whatsapp/instances/create', { instance_name: instanceName }).then((r) => r.data);

export const getInstanceQR = (instanceName) =>
  api.get(`/whatsapp/instances/qr/${instanceName}`).then((r) => r.data);

export const getInstanceStatus = (instanceName) =>
  api.get(`/whatsapp/instances/status/${instanceName}`).then((r) => r.data);

export const logoutWhatsAppInstance = () =>
  api.post('/whatsapp/instances/logout').then((r) => r.data);

export const listInstances = () =>
  api.get('/whatsapp/instances').then((r) => r.data);

// ── Start Chat / History Sync ─────────────────────────────────────────

export const getLeadsWithoutChats = () =>
  api.get('/whatsapp/leads/without-chats').then((r) => r.data);

export const syncChatHistory = (leadId) =>
  api.post(`/whatsapp/chats/${leadId}/sync-history`).then((r) => r.data);

export const getDebugContacts = (instanceName) =>
  api.get(`/whatsapp/debug/contacts/${instanceName}`).then((r) => r.data);

export const getDebugChats = (instanceName) =>
  api.get(`/whatsapp/debug/chats/${instanceName}`).then((r) => r.data);

