import HighlightList from './HighlightList';

export default function Highlights() {
  return (
    <div className="page-container">
      <h1 className="page-title">全部摘录</h1>
      <HighlightList showFilters={true} />
    </div>
  );
}
