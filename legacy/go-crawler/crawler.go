package main

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"

	"golang.org/x/net/html"
)

func fetch_bytes(
	url string,
	client *http.Client,
	retry_delay time.Duration,
	retries int,
	accept string,
	user_agent string,
) ([]byte, error) {
	for attempt := range retries {
		if attempt > 0 {
			fmt.Printf("INFO: Retry attempt %d ... \n", attempt)
		}

		req, err := http.NewRequest("GET", url, nil)
		if err != nil {
			return nil, err
		}

		if accept != "" {
			req.Header.Set("Accept", accept)
		}
		if user_agent != "" {
			req.Header.Set("User-Agent", user_agent)
		}

		resp, err := client.Do(req)
		if err != nil {
			fmt.Printf("ERROR: Failed to fetch %s with error %s \n", url, err)
			delay := min(time.Duration(attempt+1)*retry_delay, 30*time.Second)
			time.Sleep(delay)
			continue
		}

		if resp.StatusCode == 429 {
			retryAfter := resp.Header.Get("Retry-After")
			resp.Body.Close()

			if retryAfter != "" {
				seconds, err := strconv.Atoi(retryAfter)
				if err == nil {
					delay := time.Duration(seconds) * time.Second
					fmt.Printf("INFO: Rate limited. Waiting %s\n", delay)
					time.Sleep(delay)
					continue
				}
			}

			delay := min(time.Duration(attempt+1)*retry_delay, 30*time.Second)
			fmt.Printf("INFO: Rate limited. Waiting %s\n", delay)
			time.Sleep(delay)
			continue
		}
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			fmt.Printf("ERROR: Bad status %d for %s \n", resp.StatusCode, url)
			resp.Body.Close()
			continue
		}
		content_type := resp.Header.Get("Content-Type")
		if !strings.Contains(content_type, "text/html") {
			fmt.Printf("INFO: Skipping non-html file %s \n", url)
			resp.Body.Close()
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			fmt.Printf("ERROR: Reading response body %s \n", err)
			continue
		}
		return body, nil
	}
	return nil, fmt.Errorf("ERROR: Failed to fetch %s after %d retries", url, retries)
}

func canonical_url(raw_url string, base *url.URL, allowed_host string) (string, bool) {
	parsed_url, err := url.Parse(raw_url)
	if err != nil {
		return "", false
	}

	/*
		Scheme   // https
		Host     // www.tuepedia.de
		Path     // /wiki/T%C3%BCbingen
		RawQuery // a=1&b=2
		Fragment // section
	*/

	// converts relative link to absolute link
	absolute := base.ResolveReference(parsed_url)

	if absolute.Scheme != "http" && absolute.Scheme != "https" {
		return "", false
	}

	if absolute.Hostname() != allowed_host {
		return "", false
	}

	// ignore RawQuery and Fragements
	absolute.RawQuery = ""
	absolute.Fragment = ""
	absolute.Host = strings.ToLower(absolute.Host)

	// delete trailing slash
	if absolute.Path != "/" {
		absolute.Path = strings.TrimRight(absolute.Path, "/")
	}

	final_url := absolute.String()

	return final_url, true
}

func extract_urls(seen_urls map[string]bool, body []byte, current_url string, allowed_host string) ([]string, error) {
	var urls []string

	base, err := url.Parse(current_url)
	if err != nil {
		fmt.Printf("ERROR: Failed to parse url %s with error %s\n", current_url, err)
		return nil, err
	}

	reader := bytes.NewReader(body)
	tokenizer := html.NewTokenizer(reader)

	for {
		tokenType := tokenizer.Next()

		if tokenType == html.ErrorToken {
			err := tokenizer.Err()
			if err == io.EOF {
				break
			}
			return nil, err
		}

		if tokenType != html.StartTagToken {
			continue
		}

		token := tokenizer.Token()

		if token.Data != "a" {
			continue
		}

		for _, attr := range token.Attr {
			if attr.Key != "href" {
				continue
			}

			final_url, is_canonical := canonical_url(attr.Val, base, allowed_host)

			if !is_canonical {
				continue
			}

			if !seen_urls[final_url] {
				seen_urls[final_url] = true
				urls = append(urls, final_url)
			}
		}
	}

	return urls, nil
}

func url_slug(page_url string) string {
	parsed, err := url.Parse(page_url)
	if err != nil {
		return "page"
	}

	slug := strings.Trim(parsed.Path, "/")
	if slug == "" {
		slug = "index"
	}

	if parsed.RawQuery != "" {
		slug += "-" + parsed.RawQuery
	}

	replacer := strings.NewReplacer(
		"/", "-",
		"?", "-",
		"&", "-",
		"=", "-",
		":", "-",
		"@", "-",
		"%", "-",
		"#", "-",
	)

	slug = replacer.Replace(slug)
	slug = strings.Trim(slug, "-._")
	slug = strings.ToLower(slug)

	if len(slug) > 90 {
		slug = slug[:90]
		slug = strings.Trim(slug, "-._")
	}

	if slug == "" {
		slug = "page"
	}

	return slug
}

func save_html(hostname string, base_dir string, page_url string, body []byte) (string, error) {
	hash := sha256.Sum256([]byte(page_url))
	file_name := hex.EncodeToString(hash[:])[:8] + "-" + url_slug(page_url) + ".html"

	dir := filepath.Join(base_dir, hostname)

	if err := os.MkdirAll(dir, 0755); err != nil {
		return "", err
	}

	path := filepath.Join(dir, file_name)

	if err := os.WriteFile(path, body, 0644); err != nil {
		return "", err
	}

	return path, nil
}

func crawl(
	starting_url string,
	seen_urls map[string]bool,
	config Config,
	statistics *Statistics,
) (map[string]string, error) {
	client := &http.Client{
		Timeout: config.request_timeout,
	}

	base, err := url.Parse(starting_url)
	if err != nil {
		fmt.Printf("ERROR: failed to parse starting url %s with error %s \n", base, err)
		return nil, err
	}
	allowed_host := base.Hostname()

	state_path := filepath.Join(config.save_dir, allowed_host, "crawl_state.json")
	state, loaded, err := load_state(state_path)
	if err != nil {
		fmt.Printf("ERROR: failed to load intermediate state %s. \n", err)
		return nil, err
	}

	canonical_start, is_canonical := canonical_url(starting_url, base, allowed_host)
	if !is_canonical {
		fmt.Printf("ERROR: starting url %s is not canonical %s \n", base, err)
		return nil, err
	}

	var queue []string
	var head int
	var index map[string]string

	if loaded {
		queue = state.Queue
		head = state.Head
		seen_urls = state.Seen
		index = state.Index
		*statistics = state.Statistics

		if head < len(queue) {
			fmt.Printf("INFO: Resuming crawl at %s \n", queue[head])
		} else {
			fmt.Printf("INFO: Crawl state is already complete\n")
		}
	} else {
		queue = []string{canonical_start}
		head = 0
		seen_urls[canonical_start] = true
		index = map[string]string{}
	}

	for head < len(queue) {
		if config.max_pages >= 0 && len(index) >= config.max_pages {
			break
		}

		current_url := queue[head]
		head++
		statistics.inc_discovered()
		fmt.Printf("INFO: Fetching Bytes from %s \n", current_url)
		bytes, err := fetch_bytes(current_url, client, config.retry_delay, config.retries, config.accept, config.user_agent)
		if err != nil {
			fmt.Printf("ERROR: failed to fetch %s with error %s \n", current_url, err)
			statistics.inc_failed()
			continue
		}
		statistics.inc_fetched()
		// to avoid too many requests
		time.Sleep(config.request_delay)
		path, err := save_html(allowed_host, config.save_dir, current_url, bytes)
		if err != nil {
			fmt.Printf("ERROR: failed to save html %s with error %s \n", current_url, err)
			statistics.inc_failed()
			continue
		}
		index[current_url] = path
		statistics.inc_saved()

		extracted_urls, err := extract_urls(seen_urls, bytes, current_url, allowed_host)
		if err != nil {
			fmt.Printf("ERROR: failed to extract urls at %s with error %s \n", current_url, err)
			statistics.inc_failed()
			continue
		}
		queue = append(queue, extracted_urls...)

		// allows to continue at crawling state if restarted
		state := CrawlState{
			Queue:      queue,
			Head:       head,
			Seen:       seen_urls,
			Index:      index,
			Statistics: *statistics,
		}

		if err := save_state(state_path, state); err != nil {
			fmt.Printf("ERROR: failed to save crawl state: %s\n", err)
		}
	}
	return index, nil
}

func save_jsonl(path string, index map[string]string) error {
	file, err := os.Create(path)
	if err != nil {
		return err
	}
	defer file.Close()

	encoder := json.NewEncoder(file)

	for url, filePath := range index {
		row := map[string]string{
			"url":  url,
			"path": filePath,
		}

		if err := encoder.Encode(row); err != nil {
			return err
		}
	}

	return nil
}

type Config struct {
	starting_url    string
	max_pages       int
	request_timeout time.Duration
	retry_delay     time.Duration
	request_delay   time.Duration
	retries         int
	accept          string
	user_agent      string
	save_dir        string
}

func new_default_config() Config {
	return Config{
		starting_url:    "https://www.tuepedia.de",
		max_pages:       100,
		request_timeout: time.Duration(30 * time.Second),
		retry_delay:     time.Duration(10 * time.Second),
		request_delay:   time.Duration(10 * time.Millisecond),
		retries:         3,
		accept:          "text/html",
		user_agent:      "SimpleLinkCrawler/0.1",
		save_dir:        "../data2",
	}
}

type CrawlState struct {
	Queue      []string          `json:"queue"`
	Head       int               `json:"head"`
	Seen       map[string]bool   `json:"seen"`
	Index      map[string]string `json:"index"`
	Statistics Statistics        `json:"statistics"`
}

type Statistics struct {
	Fetched    int `json:"fetched"`
	Discovered int `json:"discovered"`
	Failed     int `json:"failed"`
	Saved      int `json:"saved"`
}

func (stats Statistics) print() {
	fmt.Printf("Fetched:    %d\n", stats.Fetched)
	fmt.Printf("Discovered: %d\n", stats.Discovered)
	fmt.Printf("Failed:     %d\n", stats.Failed)
	fmt.Printf("Saved:      %d\n", stats.Saved)
}
func (stats *Statistics) inc_fetched() {
	stats.Fetched++
}
func (stats *Statistics) inc_discovered() {
	stats.Discovered++
}
func (stats *Statistics) inc_failed() {
	stats.Failed++
}
func (stats *Statistics) inc_saved() {
	stats.Saved++
}

func save_state(path string, state CrawlState) error {
	dir := filepath.Dir(path)

	err := os.MkdirAll(dir, 0755)
	if err != nil {
		fmt.Printf("ERROR: failed to create folder while saving state with error %s \n", err)
		return err
	}

	data, err := json.MarshalIndent(state, "", " ")
	if err != nil {
		fmt.Printf("ERROR: failed to marshal state with error %s \n", err)
		return err
	}

	// use temp path to save data even if programm crashes
	tmp_path := path + ".tmp"

	err = os.WriteFile(tmp_path, data, 0644)
	if err != nil {
		fmt.Printf("ERROR: failed to write state with error %s \n", err)
		return err
	}

	return os.Rename(tmp_path, path)
}

func load_state(path string) (CrawlState, bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			fmt.Printf("INFO: no intermediate state found %s. \n", err)
			return CrawlState{}, false, nil
		}
		fmt.Printf("ERROR: failed to find intermediate state %s, start with new state. \n", err)
		return CrawlState{}, false, err
	}

	var state CrawlState
	err = json.Unmarshal(data, &state)
	if err != nil {
		fmt.Printf("ERROR: failed to load intermediate state %s, start with new state. \n", err)
		return CrawlState{}, false, err
	}

	fmt.Println("INFO: intermediate state was loaded successfully.")
	return state, true, nil
}

func main() {
	seen_urls := map[string]bool{}
	config := new_default_config()
	statistics := Statistics{}

	index, err := crawl(config.starting_url, seen_urls, config, &statistics)
	if err != nil {
		fmt.Printf("ERROR: failed to crawl with error %s \n", err)
		return
	}

	jsonl_path := filepath.Join(config.save_dir, "index.jsonl")
	err = save_jsonl(jsonl_path, index)
	if err != nil {
		fmt.Printf("ERROR: failed to save jsonl file with error %s \n", err)
		return
	}

	statistics.print()
}
