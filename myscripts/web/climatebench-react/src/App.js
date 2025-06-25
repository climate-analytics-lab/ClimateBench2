import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './App.css';
import Header from './components/Header';
import Navigation from './components/Navigation';
import Footer from './components/Footer';
import Overview from './pages/Overview';
import ProbabilisticScores from './pages/ProbabilisticScores';

function App() {
  return (
    <Router>
      <div className="App">
        <Header />
        <Navigation />
        <main className="main-content">
          <div className="container">
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/probabilistic-scores" element={<ProbabilisticScores />} />
            </Routes>
          </div>
        </main>
        <Footer />
      </div>
    </Router>
  );
}

export default App;
