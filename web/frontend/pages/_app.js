import React from 'react';
import Header from '../components/Header';
import Navigation from '../components/Navigation';
import Footer from '../components/Footer';
import { ColorModeProvider } from '@theme-ui/color-modes'

// Import CSS after theme-ui to ensure custom styles take precedence
import '../styles/globals.css';
import '../styles/components.css';
import '../styles/Navigation.css';
import '../styles/Overview.css';
import '../styles/ProbabilisticScores.css';
import '../styles/Map.css';
import '@carbonplan/maps/mapbox.css'

const App = ({ Component, pageProps }) => {
  return (
    <ColorModeProvider initialColorMode="light">
      <div className="App">
        <Header />
        <Navigation />
        <main className="main-content">
          <Component {...pageProps} />
        </main>
        <Footer />
      </div>
    </ColorModeProvider>
  )
}

export default App
