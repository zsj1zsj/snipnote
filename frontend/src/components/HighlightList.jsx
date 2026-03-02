import { useState, useEffect } from 'react';
import { Search, Filter } from 'lucide-react';
import api from '../api';
import HighlightCard from './HighlightCard';

export default function HighlightList({ initialHighlights = [], showFilters = true }) {
  const [highlights, setHighlights] = useState(initialHighlights);
  const [loading, setLoading] = useState(!initialHighlights.length);
  const [q, setQ] = useState('');
  const [tag, setTag] = useState('');
  const [readFilter, setReadFilter] = useState('all');
  const [tags, setTags] = useState([]);

  useEffect(() => {
    if (initialHighlights.length > 0) {
      setHighlights(initialHighlights);
      return;
    }
    loadHighlights();
  }, [q, tag, readFilter]);

  useEffect(() => {
    api.getTags().then(setTags).catch(console.error);
  }, []);

  const loadHighlights = async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (q) params.q = q;
      if (tag) params.tag = tag;
      if (readFilter !== 'all') params.read = readFilter;
      const data = await api.highlights(params);
      setHighlights(data);
    } catch (err) {
      console.error('Failed to load highlights:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = (updated) => {
    setHighlights((prev) =>
      prev.map((h) => (h.id === updated.id ? updated : h))
    );
  };

  const handleDelete = (id) => {
    setHighlights((prev) => prev.filter((h) => h.id !== id));
  };

  const filters = [
    { value: 'all', label: '全部' },
    { value: 'unread', label: '未读' },
    { value: 'read', label: '已读' },
  ];

  return (
    <div>
      {showFilters && (
        <div className="mb-6 space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索摘录内容..."
              className="search-input"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Tag filter */}
            <div className="flex items-center gap-2">
              <Filter size={16} className="text-gray-400" />
              <select
                value={tag}
                onChange={(e) => setTag(e.target.value)}
                className="select text-sm"
              >
                <option value="">所有标签</option>
                {tags.map((t) => (
                  <option key={t.name} value={t.name}>
                    {t.name} ({t.count})
                  </option>
                ))}
              </select>
            </div>

            {/* Read filter pills */}
            <div className="flex gap-1 ml-auto">
              {filters.map((f) => (
                <button
                  key={f.value}
                  onClick={() => setReadFilter(f.value)}
                  className={`filter-pill ${readFilter === f.value ? 'active' : ''}`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="spinner w-8 h-8"></div>
        </div>
      ) : highlights.length === 0 ? (
        <div className="empty-state">
          <Search size={48} className="empty-state-icon mx-auto" />
          <div className="empty-state-title">没有找到匹配的摘录</div>
          <div className="empty-state-description">试试调整搜索条件</div>
        </div>
      ) : (
        <div className="grid gap-4">
          {highlights.map((highlight) => (
            <HighlightCard
              key={highlight.id}
              highlight={highlight}
              onUpdate={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
