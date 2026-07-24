import api from './axiosInstance';

// AI Insights endpoints are under /leads/ prefix (same router prefix as leads.py but different file)
// GET /leads/{lead_id}/ai/score
// POST /leads/{lead_id}/ai/score  (triggers new analysis)
// GET /leads/{lead_id}/ai/contact-timing
// GET /leads/{lead_id}/ai/classification

export const getLeadAIScore = (leadId) =>
  api.get(`/leads/${leadId}/ai/score`).then((r) => r.data);

export const triggerLeadAIScore = (leadId) =>
  api.post(`/leads/${leadId}/ai/score`).then((r) => r.data);

export const getLeadAIContactTiming = (leadId) =>
  api.get(`/leads/${leadId}/ai/contact-timing`).then((r) => r.data);

export const getLeadAIClassification = (leadId) =>
  api.get(`/leads/${leadId}/ai/classification`).then((r) => r.data);
