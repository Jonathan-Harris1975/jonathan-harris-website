-- Only publicly verified print editions are eligible to appear on the website.
-- Do not use the Kindle ASIN as a print identifier or manufacture print ISBNs.
CREATE TABLE IF NOT EXISTS kdp_print_editions (
  ebook_id INTEGER NOT NULL REFERENCES ebooks(ebook_id),
  format TEXT NOT NULL CHECK (format IN ('paperback','hardcover')),
  state TEXT NOT NULL DEFAULT 'prepared' CHECK (state IN
    ('prepared','qa_passed','draft','submitted','uncertain','blocked','live_verified','unavailable')),
  isbn TEXT,
  print_asin TEXT,
  purchase_url TEXT,
  verified_at TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (ebook_id, format),
  CHECK (state <> 'live_verified' OR
    (isbn IS NOT NULL AND print_asin IS NOT NULL AND purchase_url IS NOT NULL AND verified_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kdp_print_editions_isbn
  ON kdp_print_editions(isbn) WHERE isbn IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_kdp_print_editions_asin
  ON kdp_print_editions(print_asin) WHERE print_asin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_kdp_print_editions_live
  ON kdp_print_editions(state, ebook_id) WHERE state = 'live_verified';
