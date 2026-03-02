import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, Clock, Star, Plus, ArrowRight } from 'lucide-react';
import api from '../api';
import HighlightCard from './HighlightCard';

export default function Home() {
  const [highlights, setHighlights] = useState([]);
  const [stats, setStats] = useState({ total: 0, due: 0, favorites: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [highlightsData, statsData] = await Promise.all([
        api.highlights({ limit: 10 }),
        api.getStats(),
      ]);
      setHighlights(highlightsData);
      setStats(statsData);
    } catch (err) {
      console.error('Failed to load data:', err);
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
    loadData();
  };

  const statCards = [
    { label: '总摘录', value: stats.total, icon: BookOpen, color: 'text-gray-700' },
    { label: '待复习', value: stats.due, icon: Clock, color: 'text-red-500', bg: 'bg-red-50' },
    { label: '收藏', value: stats.favorites, icon: Star, color: 'text-yellow-500', bg: 'bg-yellow-50' },
  ];

  if (loading) {
    return (
      <div className="page-container">
        <div className="flex items-center justify-center py-20">
          <div className="spinner w-8 h-8"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {statCards.map((stat) => (
          <div key={stat.label} className={`stat-card ${stat.bg || ''}`}>
            <div className="flex items-center justify-center gap-2 mb-2">
              <stat.icon size={20} className={stat.color} />
              <span className="stat-value">{stat.value}</span>
            </div>
            <div className="stat-label">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-2 gap-4 mb-8">
        <Link
          to="/add"
          className="card p-5 flex items-center gap-4 hover:shadow-md transition-shadow"
        >
          <div className="w-10 h-10 rounded-lg bg-gray-900 flex items-center justify-center">
            <Plus size={20} className="text-white" />
          </div>
          <div>
            <div className="font-medium text-gray-800">添加摘录</div>
            <div className="text-sm text-gray-400">手动输入或从链接导入</div>
          </div>
          <ArrowRight size={18} className="ml-auto text-gray-300" />
        </Link>
        <Link
          to="/review"
          className="card p-5 flex items-center gap-4 hover:shadow-md transition-shadow"
        >
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${stats.due > 0 ? 'bg-red-500' : 'bg-green-500'}`}>
            <Clock size={20} className="text-white" />
          </div>
          <div>
            <div className="font-medium text-gray-800">开始复习</div>
            <div className="text-sm text-gray-400">
              {stats.due > 0 ? `今日待复习 ${stats.due} 条` : '暂无待复习'}
            </div>
          </div>
          <ArrowRight size={18} className="ml-auto text-gray-300" />
        </Link>
      </div>

      {/* Recent highlights */}
      <div className="section">
        <div className="section-header">
          <h2 className="section-title">最近添加</h2>
          <Link to="/highlights" className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1">
            查看全部 <ArrowRight size={14} />
          </Link>
        </div>

        {highlights.length === 0 ? (
          <div className="empty-state">
            <BookOpen size={48} className="empty-state-icon mx-auto" />
            <div className="empty-state-title">还没有任何摘录</div>
            <div className="empty-state-description mb-4">开始添加你的第一条摘录吧</div>
            <Link to="/add" className="btn btn-primary">
              <Plus size={16} className="inline mr-2" />
              添加摘录
            </Link>
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
    </div>
  );
}
