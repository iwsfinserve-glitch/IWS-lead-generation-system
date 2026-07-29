import api from './axiosInstance';

export const sendEmailToLead = (data) =>
  api.post('/emails/send', data).then((r) => r.data);

export const getEmailHistory = (leadId) =>
  api.get(`/emails/history/${leadId}`).then((r) => r.data);
