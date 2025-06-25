import React from 'react';
import { NavLink } from 'react-router-dom';
import './Navigation.css';

const Navigation = () => {
  return (
    <nav className="nav-bar">
      <div className="container">
        <ul className="nav-links">
          <li><NavLink to="/" end>Overview</NavLink></li>
          <li><a href="#deterministic-scores">Deterministic Scores</a></li>
          <li><NavLink to="/probabilistic-scores">Probabilistic Scores</NavLink></li>
          <li><a href="#data-guide">Data Guide</a></li>
          <li><a href="#faq">FAQ</a></li>
          <li><a href="#documentation">Documentation</a></li>
        </ul>
      </div>
    </nav>
  );
};

export default Navigation; 