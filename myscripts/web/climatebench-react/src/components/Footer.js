import React from 'react';
import './Footer.css';

const Footer = () => {
  const currentYear = new Date().getFullYear();
  
  return (
    <footer className="footer">
      <div className="container">
        <p>&copy; {currentYear} Climate Analytics Lab. ClimateBench 2.0 - A benchmark for the next generation of data-driven global weather models.</p>
        <p>For questions and support, please visit our <a href="https://github.com/ClimateBench2" style={{color: '#1a73e8'}}>documentation</a> or file a <a href="https://github.com/ClimateBench2/issues" style={{color: '#1a73e8'}}>GitHub issue</a>.</p>
      </div>
    </footer>
  );
};

export default Footer; 