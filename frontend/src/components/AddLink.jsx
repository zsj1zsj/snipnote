import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Link as LinkIcon, Loader } from 'lucide-react';
import api from '../api';

export default function AddLink() {
  const navigate = useNavigate();
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.addLinkAsync(url.trim());
      navigate(`/highlight/${result.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSubmit();
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

      <div className="flex gap-3 mb-6">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入网址..."
          className="input flex-1"
          autoFocus
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !url.trim()}
          className="btn btn-primary flex items-center gap-2 px-6"
        >
          {loading ? <Loader size={18} className="animate-spin" /> : <LinkIcon size={18} />}
          添加
        </button>
      </div>

      <div className="card p-8 text-center text-gray-400 text-sm">
        <LinkIcon size={40} className="mx-auto mb-3 text-gray-300" />
        提交后立即跳转，网页内容在后台解析，稍后刷新即可查看
      </div>
    </div>
  );
}
