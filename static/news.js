/**
 * News & Events Feed Component
 * Feature #3: Real-time market news with sentiment analysis
 */

class NewsFeed {
    constructor() {
        this.currentTab = 'market';
        this.newsCache = new Map();
        this.refreshInterval = null;
        this.init();
    }

    init() {
        this.createUI();
        this.loadMarketNews();
        this.startAutoRefresh();
    }

    createUI() {
        // Create news panel in dashboard
        const dashboardContainer = document.querySelector('.dashboard-container');
        if (!dashboardContainer) {
            console.warn('News Feed: dashboard-container not found');
            return;
        }

        const newsPanel = document.createElement('div');
        newsPanel.className = 'news-panel card';
        newsPanel.innerHTML = `
            <div class="news-header">
                <h3>📰 Market News & Events</h3>
                <button class="btn-icon btn-refresh" title="Refresh news">
                    🔄
                </button>
            </div>
            
            <div class="news-tabs">
                <button class="news-tab active" data-tab="market">
                    📊 Market
                </button>
                <button class="news-tab" data-tab="watchlist">
                    ⭐ Watchlist
                </button>
                <button class="news-tab" data-tab="earnings">
                    📅 Earnings
                </button>
                <button class="news-tab" data-tab="trending">
                    🔥 Trending
                </button>
            </div>
            
            <div class="news-content">
                <div class="news-loading">
                    <div class="spinner"></div>
                    <p>Loading news...</p>
                </div>
            </div>
        `;

        // Insert as first card in dashboard
        const firstCard = dashboardContainer.querySelector('.card');
        if (firstCard) {
            dashboardContainer.insertBefore(newsPanel, firstCard);
        } else {
            dashboardContainer.appendChild(newsPanel);
        }
        
        console.log('News Feed: UI created successfully');

        // Add event listeners
        newsPanel.querySelector('.btn-refresh').addEventListener('click', () => {
            this.refreshCurrentTab();
        });

        newsPanel.querySelectorAll('.news-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });
    }

    async switchTab(tab) {
        this.currentTab = tab;
        
        // Update active tab
        document.querySelectorAll('.news-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === tab);
        });

        // Load tab content
        switch(tab) {
            case 'market':
                await this.loadMarketNews();
                break;
            case 'watchlist':
                await this.loadWatchlistNews();
                break;
            case 'earnings':
                await this.loadEarningsCalendar();
                break;
            case 'trending':
                await this.loadTrendingTickers();
                break;
        }
    }

    async loadMarketNews() {
        try {
            this.showLoading();
            
            console.log('News Feed: Loading market news...');
            
            // Check cache
            if (this.newsCache.has('market')) {
                const cached = this.newsCache.get('market');
                if (Date.now() - cached.timestamp < 120000) { // 2 min cache
                    console.log('News Feed: Using cached market news');
                    this.displayMarketNews(cached.data);
                    return;
                }
            }

            const response = await fetch('/api/news/market?limit=15', {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                }
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP ${response.status}`);
            }

            const data = await response.json();
            console.log('News Feed: Loaded', data.count, 'articles');
            this.newsCache.set('market', { data, timestamp: Date.now() });
            this.displayMarketNews(data);

        } catch (error) {
            console.error('Error loading market news:', error);
            this.showError(`Failed to load market news: ${error.message}`);
        }
    }

    displayMarketNews(data) {
        const newsContent = document.querySelector('.news-content');
        if (!newsContent) return;

        const articles = data.news || [];
        
        if (articles.length === 0) {
            newsContent.innerHTML = '<div class="news-empty">No news available</div>';
            return;
        }

        newsContent.innerHTML = `
            <div class="news-list">
                ${articles.map(article => this.createNewsCard(article)).join('')}
            </div>
        `;
    }

    createNewsCard(article) {
        const sentiment = article.sentiment || {};
        const sentimentClass = sentiment.label || 'neutral';
        
        return `
            <div class="news-card">
                <div class="news-card-header">
                    <span class="news-sentiment ${sentimentClass}" title="${sentiment.label}">
                        ${sentiment.icon || '➡️'}
                    </span>
                    <span class="news-source">${article.publisher || 'Unknown'}</span>
                    <span class="news-time">${article.published_ago || ''}</span>
                </div>
                
                <a href="${article.link}" target="_blank" class="news-title">
                    ${article.title}
                </a>
                
                ${article.source_index ? `
                    <div class="news-meta">
                        <span class="news-index">${article.source_index}</span>
                    </div>
                ` : ''}
            </div>
        `;
    }

    async loadWatchlistNews() {
        try {
            this.showLoading();
            
            console.log('News Feed: Loading watchlist news...');
            
            // Get watchlist symbols from localStorage (sidebar watchlists)
            let symbols = [];
            
            // Use the watchlistManager if available (client-side watchlists)
            if (window.watchlistManager) {
                symbols = window.watchlistManager.getAll();
                console.log('News Feed: Got symbols from watchlistManager:', symbols);
                
                // If current watchlist is empty, try to get from all watchlists
                if (symbols.length === 0) {
                    const allWatchlists = window.watchlistManager.watchlists;
                    for (const name in allWatchlists) {
                        if (name !== 'portfolio' && allWatchlists[name].length > 0) {
                            symbols = allWatchlists[name];
                            console.log(`News Feed: Using watchlist '${name}' with symbols:`, symbols);
                            break;
                        }
                    }
                }
            }
            
            console.log('News Feed: Watchlist symbols:', symbols);

            if (symbols.length === 0) {
                this.showError('No symbols in watchlist. Add symbols to your watchlist to see their news.');
                return;
            }

            // Fetch news for first 3 watchlist symbols
            console.log('News Feed: Fetching news for:', symbols.slice(0, 3));
            
            const newsPromises = symbols.slice(0, 3).map(symbol => 
                fetch(`/api/news/symbol/${symbol}?limit=5`, {
                    method: 'GET',
                    credentials: 'same-origin',
                    headers: {
                        'X-API-Key': localStorage.getItem('apiKey') || ''
                    }
                })
                .then(r => {
                    if (!r.ok) throw new Error(`Failed to fetch news for ${symbol}`);
                    return r.json();
                })
                .catch(err => {
                    console.warn(`News Feed: Error fetching news for ${symbol}:`, err);
                    return { news: [] }; // Return empty news on error
                })
            );

            const newsResults = await Promise.all(newsPromises);
            console.log('News Feed: Got news results:', newsResults);
            
            // Flatten and sort by published date
            const allNews = newsResults.flatMap(result => result.news || []);
            allNews.sort((a, b) => new Date(b.published) - new Date(a.published));

            console.log('News Feed: Total news articles:', allNews.length);
            
            if (allNews.length === 0) {
                this.showError('No news available for your watchlist symbols');
                return;
            }

            this.displayMarketNews({ news: allNews.slice(0, 15) });

        } catch (error) {
            console.error('Error loading watchlist news:', error);
            this.showError(`Failed to load watchlist news: ${error.message}`);
        }
    }

    async loadEarningsCalendar() {
        try {
            this.showLoading();
            
            const response = await fetch('/api/news/earnings?days=7', {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                }
            });

            if (!response.ok) throw new Error('Failed to fetch earnings');

            const data = await response.json();
            this.displayEarningsCalendar(data);

        } catch (error) {
            console.error('Error loading earnings:', error);
            this.showError('Failed to load earnings calendar');
        }
    }

    displayEarningsCalendar(data) {
        const newsContent = document.querySelector('.news-content');
        if (!newsContent) return;

        const earnings = data.earnings || [];
        
        if (earnings.length === 0) {
            newsContent.innerHTML = `
                <div class="news-empty">
                    <p>📅 No earnings reports in the next ${data.days_ahead} days</p>
                </div>
            `;
            return;
        }

        // Group by date
        const grouped = {};
        earnings.forEach(event => {
            if (!grouped[event.date]) {
                grouped[event.date] = [];
            }
            grouped[event.date].push(event);
        });

        newsContent.innerHTML = `
            <div class="earnings-calendar">
                ${Object.keys(grouped).map(date => `
                    <div class="earnings-day">
                        <h4 class="earnings-date">${this.formatEarningsDate(date)}</h4>
                        <div class="earnings-list">
                            ${grouped[date].map(event => `
                                <div class="earnings-card">
                                    <div class="earnings-symbol">
                                        <strong>${event.symbol}</strong>
                                        <span class="earnings-time">${event.time}</span>
                                    </div>
                                    <div class="earnings-company">${event.company}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    async loadTrendingTickers() {
        try {
            this.showLoading();
            
            const response = await fetch('/api/news/trending?limit=10', {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                }
            });

            if (!response.ok) throw new Error('Failed to fetch trending');

            const data = await response.json();
            this.displayTrending(data);

        } catch (error) {
            console.error('Error loading trending:', error);
            this.showError('Failed to load trending tickers');
        }
    }

    displayTrending(data) {
        const newsContent = document.querySelector('.news-content');
        if (!newsContent) return;

        const trending = data.trending || [];
        
        if (trending.length === 0) {
            newsContent.innerHTML = '<div class="news-empty">No trending data available</div>';
            return;
        }

        newsContent.innerHTML = `
            <div class="trending-list">
                ${trending.map((ticker, index) => `
                    <div class="trending-card">
                        <div class="trending-rank">#${index + 1}</div>
                        <div class="trending-info">
                            <div class="trending-symbol">
                                <strong>${ticker.symbol}</strong>
                                <span class="trending-name">${ticker.name}</span>
                            </div>
                            <div class="trending-stats">
                                <span class="trending-price">$${ticker.price.toFixed(2)}</span>
                                <span class="trending-change ${ticker.change >= 0 ? 'positive' : 'negative'}">
                                    ${ticker.change >= 0 ? '+' : ''}${ticker.change.toFixed(2)}%
                                </span>
                            </div>
                        </div>
                        <div class="trending-news-count">
                            📰 ${ticker.news_count} articles
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        // Add click handlers to load symbol news
        document.querySelectorAll('.trending-card').forEach((card, index) => {
            card.addEventListener('click', async () => {
                const symbol = trending[index].symbol;
                await this.loadSymbolNews(symbol);
            });
        });
    }

    async loadSymbolNews(symbol) {
        try {
            this.showLoading();
            
            const response = await fetch(`/api/news/symbol/${symbol}?limit=10`, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'X-API-Key': localStorage.getItem('apiKey') || ''
                }
            });

            if (!response.ok) throw new Error('Failed to fetch symbol news');

            const data = await response.json();
            
            // Show symbol-specific news view
            const newsContent = document.querySelector('.news-content');
            if (!newsContent) return;

            const articles = data.news || [];
            
            newsContent.innerHTML = `
                <div class="symbol-news-header">
                    <button class="btn-back">← Back</button>
                    <h4>📰 ${symbol} News</h4>
                </div>
                <div class="news-list">
                    ${articles.map(article => this.createNewsCard(article)).join('')}
                </div>
            `;

            // Add back button handler
            newsContent.querySelector('.btn-back').addEventListener('click', () => {
                this.loadTrendingTickers();
            });

        } catch (error) {
            console.error('Error loading symbol news:', error);
            this.showError('Failed to load symbol news');
        }
    }

    formatEarningsDate(dateStr) {
        const date = new Date(dateStr);
        const today = new Date();
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);

        if (date.toDateString() === today.toDateString()) {
            return '📅 Today';
        } else if (date.toDateString() === tomorrow.toDateString()) {
            return '📅 Tomorrow';
        } else {
            return date.toLocaleDateString('en-US', { 
                weekday: 'short', 
                month: 'short', 
                day: 'numeric' 
            });
        }
    }

    showLoading() {
        const newsContent = document.querySelector('.news-content');
        if (newsContent) {
            newsContent.innerHTML = `
                <div class="news-loading">
                    <div class="spinner"></div>
                    <p>Loading...</p>
                </div>
            `;
        }
    }

    showError(message) {
        const newsContent = document.querySelector('.news-content');
        if (newsContent) {
            newsContent.innerHTML = `
                <div class="news-error">
                    <p>⚠️ ${message}</p>
                </div>
            `;
        }
    }

    async refreshCurrentTab() {
        // Clear cache and reload
        this.newsCache.delete(this.currentTab);
        await this.switchTab(this.currentTab);
    }

    startAutoRefresh() {
        // Refresh every 5 minutes
        this.refreshInterval = setInterval(() => {
            if (document.visibilityState === 'visible') {
                this.refreshCurrentTab();
            }
        }, 300000); // 5 minutes
    }

    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('News Feed: Initializing (DOMContentLoaded)...');
        window.newsFeed = new NewsFeed();
    });
} else {
    console.log('News Feed: Initializing (immediate)...');
    window.newsFeed = new NewsFeed();
}
