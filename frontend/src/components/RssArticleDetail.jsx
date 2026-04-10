import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { ArrowLeft, Check, Download, Loader, ExternalLink } from 'lucide-react';
import api from '../api';
import { getCache, setCache } from '../hooks/useCache';

function markReadInListCache(articleId) {
  const listCache = getCache('rss_articles');
  if (listCache?.articles) {
    listCache.articles = listCache.articles.map(a =>
      a.id === parseInt(articleId) ? { ...a, is_read: 1 } : a
    );
    setCache('rss_articles', listCache);
  }
}

export default function RssArticleDetail() {
  const { id } = useParams();
  const cacheKey = `rss_article_${id}`;
  const cached = getCache(cacheKey);
  const [article, setArticle] = useState(cached?.article || null);
  const [content, setContent] = useState(cached?.content || null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    // If we have cached content, skip fetching
    if (cached?.article && cached?.content) {
      if (!cached.article.is_read) {
        api.toggleRssArticleRead(id);
        markReadInListCache(id);
      }
      return;
    }
    api.getRssArticle(id).then((data) => {
      setArticle(data);
      fetchContent(data.url, data);
      if (!data.is_read) {
        api.toggleRssArticleRead(id).then((result) => {
          setArticle(prev => ({ ...prev, is_read: result.is_read }));
          markReadInListCache(id);
        });
      }
    }).catch(console.error);
  }, [id]);

  const fetchContent = async (url, articleData) => {
    setLoadingContent(true);
    setError(null);
    try {
      const result = await api.parseUrl(url);
      setContent(result.content);
      setCache(cacheKey, { article: articleData, content: result.content });
    } catch (err) {
      setError(`无法加载全文: ${err.message}`);
    } finally {
      setLoadingContent(false);
    }
  };

  const handleImport = async () => {
    setImporting(true);
    try {
      const result = await api.importRssArticle(id);
      setArticle(prev => ({
        ...prev,
        is_imported: 1,
        highlight_id: result.highlight_id || prev.highlight_id,
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setImporting(false);
    }
  };

  if (!article) {
    return (
      <div className="page-container max-w-3xl text-center py-12 text-gray-400">
        <Loader size={24} className="animate-spin mx-auto mb-2" />
        加载中...
      </div>
    );
  }

  return (
    <div className="page-container max-w-3xl">
      <Link
        to="/rss/articles"
        className="inline-flex items-center gap-2 text-gray-500 hover:text-gray-700 mb-6 transition-colors"
      >
        <ArrowLeft size={18} />
        返回文章列表
      </Link>

      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-800 mb-2">{article.title}</h1>
        <div className="flex items-center gap-3 text-sm text-gray-400">
          <span>{article.feed_title}</span>
          {article.author && <span>· {article.author}</span>}
          {article.published_at && (
            <span>· {new Date(article.published_at).toLocaleDateString('zh-CN')}</span>
          )}
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-blue-500 hover:text-blue-600"
          >
            <ExternalLink size={14} />
            原文
          </a>
        </div>
      </div>

      <div className="flex gap-2 mb-6">
        {article.is_imported ? (
          article.highlight_id ? (
            <Link
              to={`/highlight/${article.highlight_id}`}
              className="btn btn-secondary flex items-center gap-2"
            >
              <Check size={16} />
              已导入 - 查看摘录
            </Link>
          ) : (
            <span className="btn btn-secondary flex items-center gap-2 opacity-60">
              <Loader size={16} className="animate-spin" />
              导入中...
            </span>
          )
        ) : (
          <button
            onClick={handleImport}
            disabled={importing}
            className="btn btn-primary flex items-center gap-2"
          >
            {importing ? <Loader size={16} className="animate-spin" /> : <Download size={16} />}
            导入为摘录
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg mb-6">
          {error}
        </div>
      )}

      <div className="card p-6">
        {loadingContent ? (
          <div className="text-center py-12 text-gray-400">
            <Loader size={24} className="animate-spin mx-auto mb-2" />
            正在加载全文...
          </div>
        ) : content ? (
          <div className="prose max-w-none">
            <ReactMarkdown
              components={{
                img: ({ node, src, alt, ...props }) => (
                  <img src={src} alt={alt} referrerPolicy="no-referrer" {...props} />
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        ) : article.summary ? (
          <div className="text-gray-600">{article.summary}</div>
        ) : (
          <div className="text-gray-400 text-center py-6">暂无内容</div>
        )}
      </div>
    </div>
  );
}
