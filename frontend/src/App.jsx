import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import Navbar from './components/Navbar';
import Home from './components/Home';
import Highlights from './components/Highlights';
import HighlightDetail from './components/HighlightDetail';
import Review from './components/Review';
import Favorites from './components/Favorites';
import TagManager from './components/TagManager';
import DailyReport from './components/DailyReport';
import AddHighlight from './components/AddHighlight';
import AddLink from './components/AddLink';
import RssFeeds from './components/RssFeeds';
import RssArticles from './components/RssArticles';
import RssArticleDetail from './components/RssArticleDetail';
import PodcastShows from './components/PodcastShows';
import PodcastEpisodes from './components/PodcastEpisodes';
import PodcastPlayer from './components/PodcastPlayer';

// Keyboard shortcuts component
function KeyboardShortcuts() {
  const navigate = useNavigate();

  useEffect(() => {
    const handleKeyDown = (e) => {
      // Ignore if user is typing in an input/textarea
      const tag = e.target.tagName.toLowerCase();
      const isInput = tag === 'input' || tag === 'textarea' || e.target.isContentEditable;

      // Ignore if Ctrl/Cmd is pressed (browser shortcuts)
      if (e.metaKey || e.ctrlKey) return;

      // Ignore if Alt is pressed
      if (e.altKey) return;

      // A - Go to add link page (global)
      if (e.key.toLowerCase() === 'a' && !isInput && window.location.pathname !== '/add-link') {
        e.preventDefault();
        navigate('/add-link');
        return;
      }

      // Z - Back to highlights (detail page)
      if (e.key.toLowerCase() === 'z' && !isInput && window.location.pathname.startsWith('/highlight/')) {
        e.preventDefault();
        navigate('/highlights');
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [navigate]);

  return null;
}

function App() {
  return (
    <BrowserRouter>
      <KeyboardShortcuts />
      <div className="min-h-screen bg-gray-50">
        <Navbar />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/highlights" element={<Highlights />} />
          <Route path="/highlight/:id" element={<HighlightDetail />} />
          <Route path="/review" element={<Review />} />
          <Route path="/favorites" element={<Favorites />} />
          <Route path="/tags" element={<TagManager />} />
          <Route path="/daily" element={<DailyReport />} />
          <Route path="/add" element={<AddHighlight />} />
          <Route path="/add-link" element={<AddLink />} />
          <Route path="/rss" element={<RssFeeds />} />
          <Route path="/rss/articles" element={<RssArticles />} />
          <Route path="/rss/article/:id" element={<RssArticleDetail />} />
          <Route path="/podcast" element={<PodcastShows />} />
          <Route path="/podcast/episodes" element={<PodcastEpisodes />} />
          <Route path="/podcast/episode/:id" element={<PodcastPlayer />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
