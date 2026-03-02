import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, BookOpen, Tag, FileText, Link as LinkIcon } from 'lucide-react';
import api from '../api';

export default function AddHighlight() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    text: '',
    source: '',
    author: '',
    location: '',
    tags: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.text.trim()) {
      setError('请输入摘录内容');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const created = await api.createHighlight(form);
      navigate(`/highlight/${created.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
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

      <h1 className="page-title">添加摘录</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg mb-6">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Text */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            <FileText size={16} className="inline mr-1" />
            摘录内容 *
          </label>
          <textarea
            value={form.text}
            onChange={(e) => handleChange('text', e.target.value)}
            placeholder="输入你想保存的内容..."
            className="textarea"
            rows={6}
            required
          />
        </div>

        {/* Source */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            <BookOpen size={16} className="inline mr-1" />
            来源
          </label>
          <input
            type="text"
            value={form.source}
            onChange={(e) => handleChange('source', e.target.value)}
            placeholder="书名、文章标题等..."
            className="input"
          />
        </div>

        {/* Author */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            作者
          </label>
          <input
            type="text"
            value={form.author}
            onChange={(e) => handleChange('author', e.target.value)}
            placeholder="作者名称"
            className="input"
          />
        </div>

        {/* Location */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            链接地址
          </label>
          <input
            type="text"
            value={form.location}
            onChange={(e) => handleChange('location', e.target.value)}
            placeholder="https://..."
            className="input"
          />
        </div>

        {/* Tags */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            <Tag size={16} className="inline mr-1" />
            标签
          </label>
          <input
            type="text"
            value={form.tags}
            onChange={(e) => handleChange('tags', e.target.value)}
            placeholder="标签1, 标签2, 标签3"
            className="input"
          />
          <p className="text-xs text-gray-400 mt-1">多个标签用逗号分隔</p>
        </div>

        {/* Submit */}
        <div className="flex gap-3 pt-4">
          <button
            type="submit"
            disabled={loading}
            className="flex-1 btn btn-primary py-3"
          >
            {loading ? '保存中...' : '保存摘录'}
          </button>
          <Link
            to="/add-link"
            className="btn btn-secondary py-3 flex items-center gap-2"
          >
            <LinkIcon size={16} />
            从链接导入
          </Link>
        </div>
      </form>
    </div>
  );
}
