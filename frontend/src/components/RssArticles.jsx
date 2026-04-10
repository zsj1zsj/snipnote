import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Check, Download, Loader, ExternalLink } from 'lucide-react';
import api from '../api';

export default function RssArticles() {
  const [searchParams] = useSearchParams();
  const initialFeedId = searchParams.get('feed_id') || '';

  const [articles, setArticles] = useState([]);
  const [feeds, setFeeds] = useState([]);
  const [feedId, setFeedId] = useState(initialFeedId);
  const [readFilter, setReadFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState({});

  const loadArticles = async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (feedId) params.feed_id = feedId;
      if (readFilter !== 'all') params.is_read = readFilter;
      const data = await api.getRssArticles(params);
      setArticles(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api.getRssFeeds().then(setFeeds).catch(console.error);
  }, []);

  useEffect(() => { loadArticles(); }, [feedId, readFilter]);

  const handleToggleRead = async (articleId) => {
    try {
      const result = await api.toggleRssArticleRead(articleId);
      setArticles(prev => prev.map(a => a.id === articleId ? { ...a, is_read: result.is_read } : a));
    } catch (err) {
      console.error(err);
    }
  };

  const handleImport = async (articleId) => {
    setImporting(prev => ({ ...prev, [articleId]: true }));
    try {
      const result = await api.importRssArticle(articleId);
      if (result.already_imported) {
        setArticles(prev => prev.map(a => a.id === articleId ? { ...a, is_imported: 1, highlight_id: result.highlight_id } : a));
      } else {
        setArticles(prev => prev.map(a => a.id === articleId ? { ...a, is_imported: 1 } : a));
      }
    } catch (err) {
      console.error(err);
    } finally {
      setImporting(prev => ({ ...prev, [articleId]: false }));
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    } catch { return ''; }
  };

  return (
    <div className="page-container max-w-3xl">
      <Link
        to="/rss"
        className="inline-flex items-center gap-2 text-gray-500 hover:text-gray-700 mb-6 transition-colors"
      >
        <ArrowLeft size={18} />
        返回订阅
      </Link>

      <h1 className="page-title">文章列表</h1>

      <div className="flex gap-3 mb-6">
        <select
          value={feedId}
          onChange={(e) => setFeedId(e.target.value)}
          className="input"
        >
          <option value="">所有订阅源</option>
          {feeds.map((f) => (
            <option key={f.id} value={f.id}>{f.title}</option>
          ))}
        </select>
        <div className="flex gap-1">
          {[
            { value: 'all', label: '全部' },
            { value: 'unread', label: '未读' },
            { value: 'read', label: '已读' },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => setReadFilter(opt.value)}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                readFilter === opt.value
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-500 hover:bg-gray-100'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">
          <Loader size={24} className="animate-spin mx-auto mb-2" />
          加载中...
        </div>
      ) : articles.length === 0 ? (
        <div className="card p-8 text-center text-gray-400 text-sm">
          暂无文章
        </div>
      ) : (
        <div className="space-y-2">
          {articles.map((article) => (
            <div
              key={article.id}
              className={`card p-4 flex items-start gap-3 ${article.is_read ? 'opacity-60' : ''}`}
            >
              <div className="flex-1 min-w-0">
                <Link
                  to={`/rss/article/${article.id}`}
                  className="font-medium text-gray-800 hover:text-blue-600 transition-colors block truncate"
                >
                  {article.title}
                </Link>
                <div className="text-sm text-gray-400 mt-1 truncate">
                  {article.feed_title}
                  {article.author && ` · ${article.author}`}
                  {article.published_at && ` · ${formatDate(article.published_at)}`}
                </div>
                {article.summary && (
                  <div className="text-sm text-gray-500 mt-1 line-clamp-2">{article.summary}</div>
                )}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                {article.is_imported ? (
                  article.highlight_id ? (
                    <Link
                      to={`/highlight/${article.highlight_id}`}
                      className="tag tag-green text-xs"
                    >
                      已导入
                    </Link>
                  ) : (
                    <span className="tag tag-green text-xs">导入中</span>
                  )
                ) : (
                  <button
                    onClick={() => handleImport(article.id)}
                    disabled={importing[article.id]}
                    className="text-gray-400 hover:text-green-600 p-1.5"
                    title="导入为摘录"
                  >
                    {importing[article.id] ? (
                      <Loader size={16} className="animate-spin" />
                    ) : (
                      <Download size={16} />
                    )}
                  </button>
                )}
                <button
                  onClick={() => handleToggleRead(article.id)}
                  className={`p-1.5 ${article.is_read ? 'text-green-500' : 'text-gray-400 hover:text-green-500'}`}
                  title={article.is_read ? '标记未读' : '标记已读'}
                >
                  <Check size={16} />
                </button>
                <a
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-gray-400 hover:text-gray-600 p-1.5"
                  title="打开原文"
                >
                  <ExternalLink size={16} />
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
