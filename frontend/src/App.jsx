import { BrowserRouter, Routes, Route } from 'react-router-dom';
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

function App() {
  return (
    <BrowserRouter>
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
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
