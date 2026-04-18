import { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Check, Download, Loader, ExternalLink, Search, CheckCheck, ArrowUpDown } from 'lucide-react';
import api from '../api';
import { getCache, setCache } from '../hooks/useCache';

const CACHE_KEY = 'rss_articles';
const PROGRESS_KEY = 'rss_read_progress';

function saveProgress(feedId, readFilter, firstVisibleId) {
  try {
    const progress = JSON.parse(localStorage.getItem(PROGRESS_KEY) || '{}');
    progress[`${feedId || 'all'}_${readFilter}`] = firstVisibleId;
    localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
  } catch {}
}

function getProgress(feedId, readFilter) {
  try {
    const progress = JSON.parse(localStorage.getItem(PROGRESS_KEY) || '{}');
    return progress[`${feedId || 'all'}_${readFilter}`] || null;
  } catch { return null; }
}

export default function RssArticles() {
  const [searchParams] = useSearchParams();
  const initialFeedId = searchParams.get('feed_id') || '';

  const cached = getCache(CACHE_KEY);
  const [articles, setArticles] = useState(cached?.articles || []);
  const [feeds, setFeeds] = useState(cached?.feeds || []);
  const [feedId, setFeedId] = useState(cached?.feedId ?? initialFeedId);
  const [readFilter, setReadFilter] = useState(cached?.readFilter || 'all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('published_at');
  const [loading, setLoading] = useState(!cached);
  const [importing, setImporting] = useState({});
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [batchImporting, setBatchImporting] = useState(false);
  const [markingAllRead, setMarkingAllRead] = useState(false);
  const articleRefs = useRef([]);
  const searchTimer = useRef(null);

  const loadArticles = async (fid, rf, search = '', sort = 'published_at') => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (fid) params.feed_id = fid;
      if (rf !== 'all') params.is_read = rf;
      if (search) params.search = search;
      if (sort !== 'published_at') params.sort = sort;
      const data = await api.getRssArticles(params);
      setArticles(data);
      setCache(CACHE_KEY, { articles: data, feeds, feedId: fid, readFilter: rf });

      // Restore reading progress
      const progressId = getProgress(fid, rf);
      if (progressId && !search) {
        setTimeout(() => {
          const idx = data.findIndex(a => a.id === progressId);
          if (idx >= 0) {
            articleRefs.current[idx]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setSelectedIndex(idx);
          }
        }, 100);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api.getRssFeeds().then((data) => {
      setFeeds(data);
      if (cached) setCache(CACHE_KEY, { ...cached, feeds: data });
    }).catch(console.error);
  }, []);

  useEffect(() => {
    loadArticles(feedId, readFilter, searchQuery, sortBy);
  }, [feedId, readFilter, sortBy]);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearchQuery(val);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      loadArticles(feedId, readFilter, val, sortBy);
    }, 400);
  };

  const updateArticles = (updater) => {
    setArticles(prev => {
      const next = updater(prev);
      setCache(CACHE_KEY, { articles: next, feeds, feedId, readFilter });
      return next;
    });
  };

  const handleToggleRead = async (articleId) => {
    try {
      const result = await api.toggleRssArticleRead(articleId);
      updateArticles(prev => prev.map(a => a.id === articleId ? { ...a, is_read: result.is_read } : a));
    } catch (err) {
      console.error(err);
    }
  };

  const handleImport = async (articleId) => {
    setImporting(prev => ({ ...prev, [articleId]: true }));
    try {
      const result = await api.importRssArticle(articleId);
      if (result.already_imported) {
        updateArticles(prev => prev.map(a => a.id === articleId ? { ...a, is_imported: 1, highlight_id: result.highlight_id } : a));
      } else {
        updateArticles(prev => prev.map(a => a.id === articleId ? { ...a, is_imported: 1 } : a));
      }
    } catch (err) {
      console.error(err);
    } finally {
      setImporting(prev => ({ ...prev, [articleId]: false }));
    }
  };

  const handleMarkAllRead = async () => {
    if (!confirm('确定要将所有文章标记为已读吗？')) return;
    setMarkingAllRead(true);
    try {
      await api.markAllRssRead(feedId ? parseInt(feedId) : null);
      updateArticles(prev => prev.map(a => ({ ...a, is_read: 1 })));
    } catch (err) {
      console.error(err);
    } finally {
      setMarkingAllRead(false);
    }
  };

  const handleBatchImport = async () => {
    const unimported = articles.filter(a => !a.is_imported).map(a => a.id);
    if (unimported.length === 0) return;
    if (!confirm(`确定要批量导入 ${unimported.length} 篇文章吗？`)) return;
    setBatchImporting(true);
    try {
      await api.batchImportRssArticles(unimported);
      updateArticles(prev => prev.map(a => unimported.includes(a.id) ? { ...a, is_imported: 1 } : a));
    } catch (err) {
      console.error(err);
    } finally {
      setBatchImporting(false);
    }
  };

  // Keyboard shortcuts
  const handleKeyDown = useCallback((e) => {
    // Skip if user is typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

    if (e.key === 'j') {
      e.preventDefault();
      setSelectedIndex(prev => {
        const next = Math.min(prev + 1, articles.length - 1);
        articleRefs.current[next]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        if (articles[next]) saveProgress(feedId, readFilter, articles[next].id);
        return next;
      });
    } else if (e.key === 'k') {
      e.preventDefault();
      setSelectedIndex(prev => {
        const next = Math.max(prev - 1, 0);
        articleRefs.current[next]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        if (articles[next]) saveProgress(feedId, readFilter, articles[next].id);
        return next;
      });
    } else if (e.key === 'm' && selectedIndex >= 0 && selectedIndex < articles.length) {
      e.preventDefault();
      handleToggleRead(articles[selectedIndex].id);
    } else if (e.key === 's' && selectedIndex >= 0 && selectedIndex < articles.length) {
      e.preventDefault();
      const article = articles[selectedIndex];
      if (!article.is_imported) handleImport(article.id);
    } else if (e.key === 'Enter' && selectedIndex >= 0 && selectedIndex < articles.length) {
      e.preventDefault();
      window.location.href = `/rss/article/${articles[selectedIndex].id}`;
    } else if (e.key === '/') {
      e.preventDefault();
      document.querySelector('[data-rss-search]')?.focus();
    }
  }, [articles, selectedIndex, feedId, readFilter]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

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

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
        <h1 className="page-title mb-0">文章列表</h1>
        <div className="flex gap-2">
          <button
            onClick={handleMarkAllRead}
            disabled={markingAllRead}
            className="btn btn-secondary flex items-center gap-2 text-sm"
            title="全部标记已读"
          >
            <CheckCheck size={16} />
            <span className="hidden sm:inline">全部已读</span>
          </button>
          <button
            onClick={handleBatchImport}
            disabled={batchImporting}
            className="btn btn-secondary flex items-center gap-2 text-sm"
            title="批量导入"
          >
            {batchImporting ? <Loader size={16} className="animate-spin" /> : <Download size={16} />}
            <span className="hidden sm:inline">批量导入</span>
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row mb-4">
        <select
          value={feedId}
          onChange={(e) => setFeedId(e.target.value)}
          className="input w-full sm:w-auto"
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
        <button
          onClick={() => setSortBy(prev => prev === 'published_at' ? 'fetched_at' : 'published_at')}
          className="btn btn-secondary flex items-center gap-1 text-sm"
          title={sortBy === 'published_at' ? '按发布时间排序' : '按抓取时间排序'}
        >
          <ArrowUpDown size={14} />
          {sortBy === 'published_at' ? '发布' : '抓取'}
        </button>
      </div>

      <div className="relative mb-6">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          data-rss-search
          type="text"
          value={searchQuery}
          onChange={handleSearchChange}
          placeholder="搜索文章标题和摘要...（按 / 聚焦）"
          className="input pl-9 w-full"
        />
      </div>

      <div className="hidden sm:block text-xs text-gray-400 mb-3">
        快捷键: <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500 font-mono">j</kbd>/<kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500 font-mono">k</kbd> 上下移动 · <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500 font-mono">m</kbd> 已读 · <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500 font-mono">s</kbd> 导入 · <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500 font-mono">Enter</kbd> 打开
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
          {articles.map((article, index) => (
            <div
              key={article.id}
              ref={el => articleRefs.current[index] = el}
              className={`card p-4 flex items-start gap-3 transition-all ${
                article.is_read ? 'opacity-60' : ''
              } ${selectedIndex === index ? 'ring-2 ring-blue-400 ring-offset-1' : ''}`}
              onClick={() => setSelectedIndex(index)}
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
                    onClick={(e) => { e.stopPropagation(); handleImport(article.id); }}
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
                  onClick={(e) => { e.stopPropagation(); handleToggleRead(article.id); }}
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
                  onClick={(e) => e.stopPropagation()}
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
