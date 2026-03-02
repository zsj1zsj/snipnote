import { useState, useEffect } from 'react';
import { Star, Search } from 'lucide-react';
import api from '../api';
import HighlightCard from './HighlightCard';

export default function Favorites() {
  const [favorites, setFavorites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');

  useEffect(() => {
    loadFavorites();
  }, [q]);

  const loadFavorites = async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (q) params.q = q;
      const data = await api.getFavorites(params);
      setFavorites(data);
    } catch (err) {
      console.error('Failed to load favorites:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = (updated) => {
    setFavorites((prev) =>
      prev.map((h) => (h.id === updated.id ? updated : h))
    );
  };

  const handleDelete = (id) => {
    setFavorites((prev) => prev.filter((h) => h.id !== id));
  };

  return (
    <div className="page-container">
      <h1 className="page-title flex items-center gap-3">
        <Star size={28} className="text-yellow-500" />
        我的收藏
      </h1>

      {/* Search */}
      <div className="relative mb-6">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜索收藏内容..."
          className="search-input"
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="spinner w-8 h-8"></div>
        </div>
      ) : favorites.length === 0 ? (
        <div className="empty-state">
          <Star size={48} className="empty-state-icon mx-auto" />
          <div className="empty-state-title">{q ? '没有找到匹配的收藏' : '还没有收藏'}</div>
          <div className="empty-state-description">
            {q ? '试试其他搜索词' : '点击摘录卡片上的星标来收藏'}
          </div>
        </div>
      ) : (
        <div className="grid gap-4">
          {favorites.map((highlight) => (
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
