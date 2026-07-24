import { useState } from 'react';
import Modal from '../common/Modal';
import { bulkImportLeads } from '../../api/leadsApi';
import toast from 'react-hot-toast';

export default function BulkImportModal({ onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setResult(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Please select a file first.');
      return;
    }
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await bulkImportLeads(formData);
      setResult(res);
      if (res.imported_count > 0) {
        toast.success(`Successfully imported ${res.imported_count} leads!`);
        onImported?.();
      } else if (res.errors && res.errors.length > 0) {
        toast.error('No leads were imported. See errors.');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to import leads.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <Modal title="Bulk Import Leads" onClose={onClose} size="md">
      <div style={{ padding: '10px 0' }}>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: 20 }}>
          Upload an Excel (.xlsx, .xls) or CSV file. The file should have headers in the first row.
          <br /><br />
          <strong>Expected Columns:</strong> Name, DOB, Phone, Email, Address, Profession, Source.
          <br /><br />
          Leads will be imported as "Unassigned".
        </p>

        {!result ? (
          <>
            <div style={{ marginBottom: 20 }}>
              <input
                type="file"
                accept=".csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel"
                onChange={handleFileChange}
                className="form-input"
              />
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!file || uploading}
                onClick={handleUpload}
              >
                {uploading ? 'Importing…' : 'Import Leads'}
              </button>
            </div>
          </>
        ) : (
          <div>
            <div style={{ padding: 15, background: 'var(--bg-elevated)', borderRadius: 8, marginBottom: 20 }}>
              <h4 style={{ marginBottom: 10 }}>Import Results</h4>
              <p>✅ <strong>Successfully Imported:</strong> {result.imported_count}</p>
              <p>⚠️ <strong>Skipped:</strong> {result.skipped_count}</p>
            </div>

            {result.errors && result.errors.length > 0 && (
              <div style={{ maxHeight: 200, overflowY: 'auto', fontSize: '0.8rem', color: 'var(--danger)', background: 'rgba(239, 68, 68, 0.1)', padding: 10, borderRadius: 6, marginBottom: 20 }}>
                <strong>Errors:</strong>
                <ul style={{ paddingLeft: 20, marginTop: 5 }}>
                  {result.errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="modal-footer">
              <button type="button" className="btn btn-primary" onClick={onClose}>Done</button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
