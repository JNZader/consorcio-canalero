/**
 * RootLayout - Root layout component for all pages.
 *
 * Handles SEO meta tags via react-helmet-async and provides
 * the common page structure (header, main, footer).
 */

import { Helmet } from 'react-helmet-async';
import Header from './Header';
import Footer from './Footer';

interface RootLayoutProps {
  /** Page title (will be suffixed with site name) */
  title: string;
  /** Meta description for SEO */
  description?: string;
  /** Open Graph image URL */
  image?: string;
  /** Open Graph type */
  type?: string;
  /** Whether to add noindex meta tag */
  noindex?: boolean;
  /** Hide the header component */
  hideHeader?: boolean;
  /** Hide the footer component */
  hideFooter?: boolean;
  /** Page content */
  children: React.ReactNode;
}

// JSON-LD structured data for the organization
const organizationSchema = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: 'Consorcio Canalero 10 de Mayo',
  description: 'Organizacion dedicada a la gestion y monitoreo de cuencas hidricas',
  url: 'https://consorcio10demayo.org',
  logo: 'https://consorcio10demayo.org/logo.svg',
  address: {
    '@type': 'PostalAddress',
    addressCountry: 'AR',
  },
  contactPoint: {
    '@type': 'ContactPoint',
    contactType: 'customer service',
  },
};

/**
 * Root layout component that wraps all pages.
 *
 * Provides:
 * - SEO meta tags via react-helmet-async
 * - JSON-LD structured data
 * - Skip link for accessibility
 * - Conditional header/footer rendering
 */
export function RootLayout({
  title,
  description = 'Sistema de gestion y monitoreo de cuencas hidricas del Consorcio Canalero 10 de Mayo. Reporta incidentes, consulta el mapa interactivo y accede a estadisticas en tiempo real.',
  image = '/og-image.jpg',
  type = 'website',
  noindex = false,
  hideHeader = false,
  hideFooter = false,
  children,
}: RootLayoutProps) {
  const fullTitle = `${title} | Consorcio Canalero 10 de Mayo`;
  const siteUrl = 'https://consorcio10demayo.org';
  const canonicalURL = `${siteUrl}${typeof window !== 'undefined' ? window.location.pathname : ''}`;
  const fullImage = image.startsWith('http') ? image : `${siteUrl}${image}`;

  return (
    <>
      <Helmet>
        {/* Primary Meta Tags */}
        <title>{fullTitle}</title>
        <meta name="title" content={fullTitle} />
        <meta name="description" content={description} />
        {noindex && <meta name="robots" content="noindex, nofollow" />}

        {/* Canonical URL */}
        <link rel="canonical" href={canonicalURL} />

        {/* Open Graph / Facebook */}
        <meta property="og:type" content={type} />
        <meta property="og:url" content={canonicalURL} />
        <meta property="og:title" content={fullTitle} />
        <meta property="og:description" content={description} />
        <meta property="og:image" content={fullImage} />
        <meta property="og:site_name" content="Consorcio Canalero 10 de Mayo" />
        <meta property="og:locale" content="es_AR" />

        {/* Twitter Card */}
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:url" content={canonicalURL} />
        <meta name="twitter:title" content={fullTitle} />
        <meta name="twitter:description" content={description} />
        <meta name="twitter:image" content={fullImage} />

        {/* JSON-LD Structured Data */}
        <script type="application/ld+json">{JSON.stringify(organizationSchema)}</script>
      </Helmet>

      {/* Skip link for accessibility */}
      <a href="#main-content" className="skip-link">
        Saltar al contenido principal
      </a>

      {!hideHeader && <Header />}

      <main id="main-content" className="flex-1">
        {children}
      </main>

      {!hideFooter && <Footer />}
    </>
  );
}

export default RootLayout;
