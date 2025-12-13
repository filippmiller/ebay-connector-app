import React from 'react';
import './HeroPage.css';

const HeroPage: React.FC = () => {
    return (
        <div className="hero-landing-page">
            <header className="hero-site-header">
                <div className="hero-container hero-header-inner">
                    <div className="hero-logo">
                        <span className="hero-logo-mark">🌱</span>
                        <span className="logo-text">Refurbish &amp; Reforest</span>
                    </div>
                    <nav className="hero-nav">
                        <a href="#how-it-works" className="hero-nav-link">How it works</a>
                        <a href="#impact" className="hero-nav-link">Impact</a>
                        <a href="#security" className="hero-nav-link">Data security</a>
                        <a href="#donate" className="hero-btn hero-btn-ghost">Donate</a>
                        <a href="/login" className="hero-btn hero-btn-ghost">Login</a>
                    </nav>
                </div>
            </header>

            <main>
                <section className="hero-section">
                    <div className="hero-container hero-layout">
                        <div className="hero-content">
                            <p className="hero-badge">Responsible laptop recycling</p>
                            <h1 className="hero-title">Donate your old laptop — and grow a tree</h1>
                            <p className="hero-subtitle">
                                We accept laptops and other devices in any condition.<br />
                                We carefully disassemble them, give usable parts a second life and send the rest to certified recycling.<br />
                                Repairs become more affordable — and for every donated laptop, we plant one tree.
                            </p>

                            <div className="hero-actions" id="donate">
                                <a href="#donate-form" className="hero-btn hero-btn-primary">Donate your device</a>
                                <a href="#how-it-works" className="hero-btn hero-btn-secondary">How it works</a>
                            </div>
                            <p className="hero-small">Laptops, PCs, phones, servers — in any condition.</p>

                            <ul className="hero-benefits">
                                <li className="hero-benefit">
                                    <span className="hero-benefit-icon">♻</span>
                                    <span>Nothing goes to landfill – only reuse and responsible recycling.</span>
                                </li>
                                <li className="hero-benefit">
                                    <span className="hero-benefit-icon">💻</span>
                                    <span>Tested used parts make repairing old computers more affordable.</span>
                                </li>
                                <li className="hero-benefit">
                                    <span className="hero-benefit-icon">🛡</span>
                                    <span>All data wiped according to NIST SP 800-88 guidelines.</span>
                                </li>
                                <li className="hero-benefit">
                                    <span className="hero-benefit-icon">🌳</span>
                                    <span><strong>1 laptop = 1 tree</strong> through our tree-planting partners.</span>
                                </li>
                            </ul>

                            <div className="data-security-pill">
                                <span className="pill-icon">🛡</span>
                                <p className="pill-text">
                                    We wipe or destroy all storage devices following NIST SP 800-88 Rev.1 (Clear / Purge / Destroy).
                                </p>
                            </div>
                        </div>

                        <div className="hero-visual">
                            <div className="hero-illustration">
                                <div className="laptop-base"></div>
                                <div className="laptop-screen"></div>
                                <div className="laptop-board"></div>
                                <div className="laptop-battery"></div>
                                <div className="tree trunk"></div>
                                <div className="tree canopy canopy-1"></div>
                                <div className="tree canopy canopy-2"></div>
                                <div className="tree canopy canopy-3"></div>
                            </div>

                            <div className="hero-stats-card">
                                <p className="stat-label">E-waste diverted</p>
                                <p className="stat-value">1,250 kg</p>
                                <p className="stat-label">Trees planted</p>
                                <p className="stat-value">312</p>
                            </div>

                            <div className="hero-partners">
                                <p className="partners-label">Working with recycling &amp; tree-planting partners</p>
                                <div className="partners-logos">
                                    <div className="partner-logo placeholder">Recycling partner</div>
                                    <div className="partner-logo placeholder">Tree partner</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                <section id="how-it-works" className="hero-generic-section section-muted">
                    <div className="hero-container section-inner">
                        <h2>How it works</h2>
                        <div className="steps-grid">
                            <div className="step">
                                <div className="step-number">1</div>
                                <h3>Donate your device</h3>
                                <p>Fill in a quick form, tell us what you want to donate, and we arrange collection or drop-off.</p>
                            </div>
                            <div className="step">
                                <div className="step-number">2</div>
                                <h3>We disassemble &amp; secure</h3>
                                <p>We safely wipe or destroy all storage devices following NIST SP 800-88 and carefully disassemble each device.</p>
                            </div>
                            <div className="step">
                                <div className="step-number">3</div>
                                <h3>Reuse, recycle, reforest</h3>
                                <p>Usable parts go into affordable repairs, the rest is recycled — and for every laptop, we plant one tree.</p>
                            </div>
                        </div>
                    </div>
                </section>

                <section id="impact" className="hero-generic-section">
                    <div className="hero-container section-inner impact-layout">
                        <div className="impact-text">
                            <h2>Making repairs cheaper, not landfills bigger</h2>
                            <p>
                                Our mission is to keep devices in use for as long as possible. By testing and reselling used parts,
                                we help people and small businesses repair existing computers at a lower cost instead of buying new ones.
                            </p>
                            <p>
                                Every device you donate reduces electronic waste and extends the life of hardware that would otherwise
                                end up on a scrap pile.
                            </p>
                        </div>
                        <div className="impact-highlights">
                            <div className="impact-card">
                                <p className="impact-number">90%</p>
                                <p className="impact-label">Average component reuse potential per donated laptop*</p>
                            </div>
                            <div className="impact-card">
                                <p className="impact-number">1</p>
                                <p className="impact-label">Tree planted for every donated laptop</p>
                            </div>
                            <p className="impact-note">*Illustrative numbers for mockup purposes.</p>
                        </div>
                    </div>
                </section>

                <section id="security" className="hero-generic-section section-muted">
                    <div className="hero-container section-inner security-layout">
                        <div className="security-text">
                            <h2>Your data is wiped to global standards</h2>
                            <p>
                                Before any device leaves our facility, we sanitize all storage media in line with
                                <strong>NIST SP 800-88 Rev.1 (Guidelines for Media Sanitization)</strong>.
                            </p>
                            <ul className="security-list">
                                <li><strong>Clear:</strong> logical overwrite of data so it cannot be recovered with standard tools.</li>
                                <li><strong>Purge:</strong> advanced sanitization (for example, cryptographic erase) for higher sensitivity data.</li>
                                <li><strong>Destroy:</strong> physical destruction of the storage device when reuse is not an option.</li>
                            </ul>
                            <p>
                                For organisational donors, we can provide confirmation of media sanitization or destruction on request.
                            </p>
                        </div>
                        <div className="security-side">
                            <div className="security-card">
                                <div className="security-icon">🛡</div>
                                <h3>Data-first process</h3>
                                <p>Data sanitization is the very first step in our workflow — not an afterthought.</p>
                            </div>
                            <div className="security-card">
                                <div className="security-icon">📄</div>
                                <h3>Certificates for donors</h3>
                                <p>We can generate per-batch confirmation for devices we sanitize or destroy.</p>
                            </div>
                        </div>
                    </div>
                </section>

                <section id="donate-form" className="hero-generic-section section-cta">
                    <div className="hero-container section-inner cta-inner">
                        <div className="cta-text">
                            <h2>Ready to donate your device?</h2>
                            <p>Leave your contact details and a short description of what you’d like to donate. We’ll get back to you with the next steps.</p>
                        </div>
                        <form className="cta-form" onSubmit={(e) => e.preventDefault()}>
                            <div className="form-row">
                                <label htmlFor="name">Name</label>
                                <input id="name" name="name" type="text" placeholder="Your name" />
                            </div>
                            <div className="form-row">
                                <label htmlFor="email">Email</label>
                                <input id="email" name="email" type="email" placeholder="you@example.com" />
                            </div>
                            <div className="form-row">
                                <label htmlFor="devices">What would you like to donate?</label>
                                <textarea id="devices" name="devices" rows={3} placeholder="e.g. 10 laptops, 3 desktop PCs, 5 phones"></textarea>
                            </div>
                            <button type="submit" className="hero-btn hero-btn-primary hero-btn-full">Submit donation request</button>
                            <p className="form-note">This is a mockup form. In production, connect it to your backend or form provider.</p>
                        </form>
                    </div>
                </section>
            </main>

            <footer className="site-footer">
                <div className="hero-container footer-inner">
                    <p className="footer-copy">© 2025 Refurbish &amp; Reforest. All rights reserved.</p>
                    <p className="footer-meta">Hero mockup — for internal design and development only.</p>
                </div>
            </footer>
        </div>
    );
};

export default HeroPage;
