import { useState, useEffect } from 'react';
import Modal from '../common/Modal';
import { createUser, updateUser } from '../../api/usersApi';
import { getUsers } from '../../api/usersApi';
import toast from 'react-hot-toast';

export default function ManageUserModal({ user: existingUser, onClose, onSaved }) {
  const isEdit = !!existingUser;
  const [managers, setManagers] = useState([]);
  const [form, setForm] = useState({
    name:       existingUser?.name || '',
    email:      existingUser?.email || '',
    password:   '',
    role:       existingUser?.role || 'sales_rep',
    manager_id: existingUser?.manager_id || '',
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getUsers().then((u) => setManagers(u.filter((x) => x.role === 'manager'))).catch(() => {});
  }, []);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim()) { toast.error('Name and email are required'); return; }
    if (!isEdit && !form.password) { toast.error('Password is required for new users'); return; }

    setSaving(true);
    try {
      const payload = { name: form.name.trim(), email: form.email.trim(), role: form.role };
      if (form.password) payload.password = form.password;
      if (form.manager_id) payload.manager_id = parseInt(form.manager_id);

      if (isEdit) {
        await updateUser(existingUser.id, payload);
        toast.success('User updated!');
      } else {
        await createUser(payload);
        toast.success('User created!');
      }
      onSaved?.();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Operation failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={isEdit ? 'Edit User' : 'Create New User'} onClose={onClose}>
      <form onSubmit={handleSubmit} id="manage-user-form">
        <div className="form-group">
          <label className="form-label">Full Name *</label>
          <input className="form-input" placeholder="Jane Smith" value={form.name}
            onChange={(e) => set('name', e.target.value)} id="user-name" />
        </div>
        <div className="form-group">
          <label className="form-label">Email *</label>
          <input className="form-input" type="email" placeholder="jane@iwsfinserve.com" value={form.email}
            onChange={(e) => set('email', e.target.value)} id="user-email" />
        </div>
        <div className="form-group">
          <label className="form-label">{isEdit ? 'New Password (leave blank to keep)' : 'Password *'}</label>
          <input className="form-input" type="password" placeholder={isEdit ? '••••••••' : 'Min. 6 characters'} value={form.password}
            onChange={(e) => set('password', e.target.value)} id="user-password" />
        </div>
        <div className="form-group">
          <label className="form-label">Role</label>
          <select className="form-select" value={form.role} onChange={(e) => set('role', e.target.value)} id="user-role">
            <option value="sales_rep">Sales Rep</option>
            <option value="manager">Manager</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        {form.role === 'sales_rep' && managers.length > 0 && (
          <div className="form-group">
            <label className="form-label">Reporting Manager</label>
            <select className="form-select" value={form.manager_id} onChange={(e) => set('manager_id', e.target.value)} id="user-manager">
              <option value="">No manager assigned</option>
              {managers.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        )}
        <div className="modal-footer">
          <button type="button" className="btn btn-ghost" onClick={onClose} id="user-cancel">Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving} id="user-submit">
            {saving ? (isEdit ? 'Updating…' : 'Creating…') : (isEdit ? 'Update User' : 'Create User')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
