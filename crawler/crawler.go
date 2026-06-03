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

		resp, err := client.Do(req)
		if err != nil {
			fmt.Printf("ERROR: Failed to fetch %s with error %s\n", url, err)
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

			href, err := url.Parse(attr.Val)
			if err != nil {
				continue
			}

			absolute := base.ResolveReference(href)
			absolute.RawQuery = ""
			absolute.Fragment = ""

			if absolute.Scheme != "http" && absolute.Scheme != "https" {
				continue
			}

			if absolute.Hostname() != allowed_host {
				continue
			}

			final_url := absolute.String()

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
	max_pages int,
	request_timeout time.Duration,
	retry_delay time.Duration,
	request_delay time.Duration,
	retries int,
	accept string,
	save_dir string,
) (map[string]string, error) {

	client := &http.Client{
		Timeout: request_timeout,
	}
	start, err := url.Parse(starting_url)
	if err != nil {
		fmt.Printf("ERROR: failed to parse starting url %s with error %s \n", start, err)
		return nil, err
	}
	allowed_host := start.Hostname()

	queue := []string{starting_url}
	head := 0
	seen_urls[starting_url] = true

	index := map[string]string{}

	for head < len(queue) {
		if max_pages >= 0 && len(index) >= max_pages {
			break
		}

		current_url := queue[head]
		head++
		fmt.Printf("INFO: Fetching Bytes from %s \n", current_url)
		bytes, err := fetch_bytes(current_url, client, retry_delay, retries, accept)
		if err != nil {
			fmt.Printf("ERROR: failed to fetch %s with error %s \n", current_url, err)
			continue
		}
		// to avoid too many requests
		time.Sleep(request_delay)
		path, err := save_html(allowed_host, save_dir, current_url, bytes)
		if err != nil {
			fmt.Printf("ERROR: failed to save html %s with error %s \n", current_url, err)
			continue
		}
		index[current_url] = path

		extracted_urls, err := extract_urls(seen_urls, bytes, current_url, allowed_host)
		if err != nil {
			fmt.Printf("ERROR: failed to extract urls at %s with error %s \n", current_url, err)
			continue
		}
		queue = append(queue, extracted_urls...)
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

func main() {
	seen_urls := map[string]bool{}

	url := "https://www.tuepedia.de"
	request_timeout := time.Duration(30 * time.Second)
	retry_delay := time.Duration(10 * time.Second)
	request_delay := time.Duration(25 * time.Millisecond)
	retries := 3
	accept := "text/html"
	html_path := "../data2"
	jsonl_path := filepath.Join(html_path, "index.jsonl")
	max_pages := 100

	index, err := crawl(url, seen_urls, max_pages, request_timeout, retry_delay, request_delay, retries, accept, html_path)
	if err != nil {
		fmt.Printf("ERROR: failed to crawl with error %s \n", err)
		return
	}

	err = save_jsonl(jsonl_path, index)
	if err != nil {
		fmt.Printf("ERROR: failed to save jsonl file with error %s \n", err)
		return
	}
}
