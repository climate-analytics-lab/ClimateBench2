import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/router';

const Navigation = () => {
  const router = useRouter();

  const isActive = (path) => {
    return router.pathname === path;
  };

  const navItems = [
    { href: '/overview', label: 'Overview' },
    { href: '/probabilistic-scores', label: 'Probabilistic Scores' },
    { href: '/map', label: 'Climate Map' }
  ];

  return (
    <nav className="navigation" role="navigation" aria-label="Main navigation">
      <div className="nav-container">
        <ul className="nav-list">
          {navItems.map((item) => (
            <li key={item.href} className="nav-item">
              <Link href={item.href} passHref>
                <a
                  className={`nav-link ${isActive(item.href) ? 'active' : ''}`}
                  aria-current={isActive(item.href) ? 'page' : undefined}
                >
                  {item.label}
                </a>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
};

export default Navigation; 