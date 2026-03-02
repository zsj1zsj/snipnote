import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Link as LinkIcon, Loader, FileText } from 'lucide-react';
import api from '../api';

export default function AddLink() {
  const navigate = useNavigate();
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState(null);
  const [parsed, setParsed] = useState(null);

  const handleParse = async () => {
    if (!url.trim()) return;
    setParsing(true);
    setError(null);
    try {
      const result = await api.parseUrl(url);
      setParsed(result);
    } catch (err) {
      setError(err.message);
      setParsed(null);
    } finally {
      setParsing(false);
    }
  };

  const handleSave = async () => {
    if (!parsed) return;
    setLoading(true);
    setError(null);
    try {
      const created = await api.createHighlight({
        text: parsed.content,
        source: parsed.title,
        location: url,
      });
      navigate(`/highlight/${created.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container max-w-2xl">
      <Link
        to="/highlights"
        className="inline-flex items-center gap-2 text-gray-500 hover:text-gray-700 mb-6 transition-colors"
      >
        <ArrowLeft size={18} />
        返回列表
      </Link>

      <h1 className="page-title">从链接添加</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg mb-6">
          {error}
        </div>
      )}

      {/* URL input */}
      <div className="flex gap-3 mb-6">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="输入网址..."
          className="input flex-1"
        />
        <button
          onClick={handleParse}
          disabled={parsing || !url.trim()}
          className="btn btn-primary flex items-center gap-2 px-6"
        >
          {parsing ? <Loader size={18} className="animate-spin" /> : <LinkIcon size={18} />}
          解析
        </button>
      </div>

      {/* Parsed content preview */}
      {parsed && (
        <div className="card p-6">
          <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <FileText size={18} className="text-gray-400" />
            {parsed.title}
          </h2>
          <div className="prose-custom max-h-96 overflow-y-auto text-sm mb-6 p-4 bg-gray-50 rounded-lg">
            {parsed.content.slice(0, 2000)}
            {parsed.content.length > 2000 && '...'}
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleSave}
              disabled={loading}
              className="flex-1 btn btn-primary py-3"
            >
              {loading ? '保存中...' : '保存为摘录'}
            </button>
            <Link
              to="/add"
              className="btn btn-secondary py-3"
            >
              手动输入
            </Link>
          </div>
        </div>
      )}

      {!parsed && !parsing && (
        <div className="card p-12 text-center">
          <LinkIcon size={48} className="mx-auto text-gray-300 mb-4" />
          <div className="text-gray-500">输入网址，解析网页内容</div>
        </div>
      )}
    </div>
  );
}
