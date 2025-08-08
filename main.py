import requests
from bs4 import BeautifulSoup
import json
import time
import csv
from urllib.parse import urljoin
import re
import os
from pathlib import Path
from PIL import Image
import yt_dlp


class IBACocktailScraper:
    def __init__(self):
        self.base_url = "https://iba-world.com"
        self.all_cocktails_url = "https://iba-world.com/cocktails/all-cocktails/"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

    def get_cocktail_links(self):
        """Get all cocktail links from the main page"""
        cocktail_links = []
        page = 1

        while True:
            print(f"Scraping page {page}...")
            if page == 1:
                url = self.all_cocktails_url
            else:
                url = f"{self.all_cocktails_url}page/{page}/"

            try:
                response = self.session.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Look for cocktail cards - these might be in specific containers
                # Try to find links that go to individual cocktail pages
                page_links = []

                # Look for cocktail links in various possible structures
                possible_selectors = [
                    'a[href*="/iba-cocktail/"]',
                    'a[href*="/cocktail/"]',
                    ".cocktail-card a",
                    ".cocktail-item a",
                    '[class*="cocktail"] a',
                ]

                for selector in possible_selectors:
                    links = soup.select(selector)
                    if links:
                        for link in links:
                            href = link.get("href")
                            if href:
                                full_url = urljoin(self.base_url, href)
                                raw_text = link.get_text(strip=True)

                                # Clean the name by removing view counts and categories
                                name, views = self.clean_cocktail_name(raw_text)

                                # Extract category from surrounding elements
                                category = self.extract_category(link)

                                if name and full_url not in [
                                    c["url"] for c in cocktail_links
                                ]:
                                    cocktail_links.append(
                                        {
                                            "name": name,
                                            "url": full_url,
                                            "category": category,
                                            "views": views,
                                        }
                                    )
                                    page_links.append(name)
                        break  # If we found links with one selector, use those

                # If no specific cocktail links found, look for any links containing cocktail names
                if not page_links:
                    all_links = soup.find_all("a", href=True)
                    for link in all_links:
                        href = link.get("href")
                        raw_text = link.get_text(strip=True)

                        if (
                            href
                            and (
                                "cocktail" in href.lower()
                                or "iba-cocktail" in href.lower()
                            )
                            and raw_text
                            and len(raw_text)
                            < 100  # Increased to account for view counts
                            and len(raw_text) > 2
                        ):

                            full_url = urljoin(self.base_url, href)
                            if full_url not in [c["url"] for c in cocktail_links]:
                                name, views = self.clean_cocktail_name(raw_text)
                                category = self.extract_category(link)

                                if name:  # Only add if we got a clean name
                                    cocktail_links.append(
                                        {
                                            "name": name,
                                            "url": full_url,
                                            "category": category,
                                            "views": views,
                                        }
                                    )
                                    page_links.append(name)

                if not page_links:  # No new cocktails found
                    break

                print(f"Found {len(page_links)} cocktails on page {page}")
                page += 1
                time.sleep(0.5)  # Be respectful to the server

                # If we only found a few links, we might be at the end
                if len(page_links) < 5:
                    break

            except requests.exceptions.RequestException as e:
                print(f"Error fetching page {page}: {e}")
                break

        return cocktail_links

    def clean_cocktail_name(self, raw_text):
        """Extract clean cocktail name and view count from raw text"""
        if not raw_text:
            return None, None

        # Extract view count (pattern like "108.9K views" or "1.2M views")
        views_match = re.search(
            r"([0-9]+(?:\.[0-9]+)?[KM]?)\s*views?", raw_text, re.IGNORECASE
        )
        views = views_match.group(1) if views_match else None

        # Remove view count from the text
        clean_text = re.sub(
            r"[0-9]+(?:\.[0-9]+)?[KM]?\s*views?", "", raw_text, flags=re.IGNORECASE
        )

        # Remove common category names that might be attached (case-insensitive)
        category_patterns = [
            r"The\s+unforgettables?",
            r"Contemporary\s+Classics?",
            r"New\s+Era\s+Drinks?",
            r"New\s+Era",  # Handle "New Era" without "Drinks"
            r"The\s+Unforgettables?",
            r"Unforgettables?",
        ]

        for pattern in category_patterns:
            clean_text = re.sub(pattern, "", clean_text, flags=re.IGNORECASE)

        # Clean up extra whitespace and common separators
        clean_text = re.sub(r"[\s\-_]+", " ", clean_text).strip()

        # Remove any remaining non-alphabetic characters at the start/end
        clean_text = re.sub(r"^[^a-zA-Z]+|[^a-zA-Z0-9\s']+$", "", clean_text).strip()

        # If the name is too short or empty after cleaning, return None
        if not clean_text or len(clean_text) < 2:
            return None, views

        return clean_text, views

    def normalize_method_text(self, method_text):
        """Normalize method text to have single newlines between steps"""
        if not method_text:
            return ""

        # Split by any combination of newlines and whitespace
        lines = re.split(r"\n+", method_text.strip())

        # Clean each line and filter out empty ones
        clean_lines = []
        for line in lines:
            line = line.strip()
            if line:  # Only keep non-empty lines
                clean_lines.append(line)

        # Join with single newlines
        return "\n".join(clean_lines)

    def extract_category(self, link_element):
        """Extract category from surrounding elements"""
        category = ""

        # Look in parent elements for category indicators
        current = link_element
        for _ in range(5):  # Look up to 5 levels up
            if current:
                text = current.get_text().lower()
                if "unforgettable" in text:
                    return "The Unforgettables"
                elif "contemporary" in text:
                    return "Contemporary Classics"
                elif "new era" in text:
                    return "New Era"
                current = current.parent
            else:
                break

        return category

    def scrape_cocktail_recipe(self, cocktail_url, cocktail_name):
        """Scrape a single cocktail recipe"""
        try:
            response = self.session.get(cocktail_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            recipe = {
                "url": cocktail_url,
                "name": cocktail_name,
                "category": "",
                "views": None,
                "ingredients": [],
                "method": "",
                "garnish": "",
                "image": None,
                "video": None,
            }

            # Get the full page text to work with
            page_text = soup.get_text()

            # Extract ingredients - look for lines after "Ingredients"
            ingredients_match = re.search(
                r"Ingredients\s*\n(.*?)(?=Method|Preparation|Glass|Garnish|$)",
                page_text,
                re.DOTALL | re.IGNORECASE,
            )
            if ingredients_match:
                ingredients_text = ingredients_match.group(1).strip()
                # Split by lines and clean up
                ingredients = []
                for line in ingredients_text.split("\n"):
                    line = line.strip()
                    if line and not line.lower().startswith(
                        ("method", "preparation", "glass", "garnish")
                    ):
                        # Remove leading dashes or bullets
                        line = re.sub(r"^[-•*]\s*", "", line)
                        if line:
                            ingredients.append(line)
                recipe["ingredients"] = ingredients

            # Extract method/preparation - look for complete method text
            method_match = re.search(
                r"Method\s*\n(.*?)(?=\n\s*Garnish|$)",
                page_text,
                re.DOTALL | re.IGNORECASE,
            )
            if method_match:
                method_text = method_match.group(1).strip()
                # Clean up the method text by removing any trailing incomplete sentences
                # and ensuring we capture the complete instructions
                method_lines = method_text.split("\n")
                clean_method_lines = []
                for line in method_lines:
                    line = line.strip()
                    if line and not line.lower().startswith(("glass", "garnish")):
                        clean_method_lines.append(line)
                recipe["method"] = self.normalize_method_text(
                    "\n".join(clean_method_lines)
                )

            # If no "Method", look for "Preparation"
            if not recipe["method"]:
                prep_match = re.search(
                    r"Preparation\s*\n(.*?)(?=\n\s*Garnish|$)",
                    page_text,
                    re.DOTALL | re.IGNORECASE,
                )
                if prep_match:
                    prep_text = prep_match.group(1).strip()
                    prep_lines = prep_text.split("\n")
                    clean_prep_lines = []
                    for line in prep_lines:
                        line = line.strip()
                        if line and not line.lower().startswith(("glass", "garnish")):
                            clean_prep_lines.append(line)
                    recipe["method"] = self.normalize_method_text(
                        "\n".join(clean_prep_lines)
                    )

            # Extract garnish
            garnish_match = re.search(
                r"Garnish[:\s]*\n?(.*?)(?=\n\n|$)", page_text, re.DOTALL | re.IGNORECASE
            )
            if garnish_match:
                recipe["garnish"] = garnish_match.group(1).strip()

            # Try alternative parsing using HTML structure
            if not recipe["ingredients"]:
                # Look for structured ingredients in HTML
                ingredient_elements = soup.find_all(["li", "p"])
                for elem in ingredient_elements:
                    text = elem.get_text(strip=True)
                    if text and (
                        "ml" in text.lower()
                        or "cl" in text.lower()
                        or "oz" in text.lower()
                        or "dash" in text.lower()
                        or "tsp" in text.lower()
                        or "tbsp" in text.lower()
                    ):
                        if text not in recipe["ingredients"]:
                            recipe["ingredients"].append(text)

            # Scrape image (single URL)
            recipe["image"] = self.scrape_image(soup)

            # Scrape video link (single URL)
            recipe["video"] = self.scrape_video_link(soup)

            return recipe

        except requests.exceptions.RequestException as e:
            print(f"Error scraping {cocktail_url}: {e}")
            return None
        except Exception as e:
            print(f"Error parsing {cocktail_url}: {e}")
            return None

    def scrape_image(self, soup):
        """Extract the primary cocktail image URL from the page"""
        image_url = None

        # Look for various image selectors that might contain cocktail photos
        image_selectors = [
            'img[src*="cocktail"]',
            'img[src*="iba-cocktail"]',
            ".cocktail-image img",
            ".recipe-image img",
            'img[alt*="cocktail"]',
            'img[class*="cocktail"]',
            'img[src*=".webp"]',
            'img[src*=".jpg"]',
            'img[src*=".png"]',
        ]

        # Get the cocktail name from the page title or URL to match the correct image
        page_title = soup.find("title")
        cocktail_name_from_title = ""
        if page_title:
            cocktail_name_from_title = page_title.get_text().lower()

        # Also try to get cocktail name from URL
        current_url = soup.find("link", {"rel": "canonical"})
        cocktail_name_from_url = ""
        if current_url:
            url_text = current_url.get("href", "").lower()
            # Extract cocktail name from URL pattern like /iba-cocktail/alexander/
            url_parts = url_text.split("/")
            for part in url_parts:
                if part and part != "iba-cocktail" and len(part) > 2:
                    cocktail_name_from_url = part
                    break

        for selector in image_selectors:
            img_elements = soup.select(selector)
            for img in img_elements:
                src = img.get("src")
                alt = img.get("alt", "")

                if src:
                    # Convert relative URLs to absolute
                    if src.startswith("/"):
                        src = urljoin(self.base_url, src)
                    elif not src.startswith("http"):
                        src = urljoin(self.base_url, src)

                    # Filter out logos, icons, and other cocktail images
                    if any(
                        skip_word in src.lower()
                        for skip_word in ["logo", "icon", "favicon", "avatar"]
                    ):
                        continue

                    # Check if this image matches the current cocktail
                    src_lower = src.lower()
                    is_primary_image = False

                    # If we have cocktail name from URL, check if image URL contains it
                    if cocktail_name_from_url and cocktail_name_from_url in src_lower:
                        is_primary_image = True
                    # If no URL match but this is the first cocktail image found, use it
                    elif not image_url and "cocktail" in src_lower:
                        is_primary_image = True

                    # Return the first primary image URL found
                    if is_primary_image:
                        return src

            # If we found a primary image, stop looking
            if image_url:
                break

        return image_url

    def scrape_video_link(self, soup):
        """Extract the primary video link for cocktail preparation"""
        video_url = None

        # Look for various video link patterns
        video_selectors = [
            'a[href*="youtube.com"]',
            'a[href*="youtu.be"]',
            'a[href*="vimeo.com"]',
            'a[href*="video"]',
            'iframe[src*="youtube"]',
            'iframe[src*="vimeo"]',
            ".video-link",
            '[class*="video"] a',
        ]

        for selector in video_selectors:
            elements = soup.select(selector)
            for element in elements:
                if element.name == "iframe":
                    src = element.get("src")
                    if src:
                        # Filter out general channel embeds, keep specific videos
                        if "watch?v=" in src or "embed/" in src:
                            return src
                else:
                    href = element.get("href")
                    title = element.get_text(strip=True)

                    if href:
                        # Convert relative URLs to absolute
                        if href.startswith("/"):
                            href = urljoin(self.base_url, href)
                        elif not href.startswith("http"):
                            href = urljoin(self.base_url, href)

                        # Filter out general YouTube channel links
                        # Keep only specific video links (contain watch?v= or youtu.be/)
                        # Also filter by title to avoid general "Youtube" links
                        is_specific_video = False

                        if "watch?v=" in href or "youtu.be/" in href:
                            is_specific_video = True
                        elif (
                            "vimeo.com/" in href
                            and "/channels/" not in href
                            and "/users/" not in href
                        ):
                            is_specific_video = True
                        elif title and any(
                            keyword in title.lower()
                            for keyword in [
                                "play",
                                "video",
                                "watch",
                                "preparation",
                                "recipe",
                                "how to",
                            ]
                        ):
                            is_specific_video = True

                        # Exclude general channel links and generic "Youtube" titles
                        if (
                            "/channel/" in href
                            or "/user/" in href
                            or title.lower()
                            in ["youtube", "youtube channel", "channel"]
                            or "youtube.com/c/" in href
                        ):
                            is_specific_video = False

                        # Return the first specific video URL found
                        if is_specific_video:
                            return href

        return video_url

    def setup_media_folders(self):
        """Create images and videos folders if they don't exist"""
        Path("images").mkdir(exist_ok=True)
        Path("videos").mkdir(exist_ok=True)
        print("Created media folders: images/ and videos/")

    def download_image(self, image_url, cocktail_name):
        """Download cocktail image and save locally"""
        if not image_url:
            return None

        try:
            # Create safe filename from cocktail name
            safe_name = re.sub(r"[^a-zA-Z0-9\s-]", "", cocktail_name)
            safe_name = re.sub(r"\s+", "_", safe_name.strip())

            # Get file extension from URL
            extension = ".webp"  # Default for IBA images
            if "." in image_url.split("/")[-1]:
                extension = "." + image_url.split(".")[-1].split("?")[0]

            filename = f"images/{safe_name}{extension}"

            # Download image
            response = self.session.get(image_url)
            response.raise_for_status()

            # Save image
            with open(filename, "wb") as f:
                f.write(response.content)

            print(f"  Downloaded image: {filename}")
            return filename

        except Exception as e:
            print(f"  Error downloading image for {cocktail_name}: {e}")
            return None

    def download_video(self, video_url, cocktail_name):
        """Download YouTube video and save locally"""
        if not video_url or "youtube.com" not in video_url:
            return None

        try:
            # Create safe filename from cocktail name
            safe_name = re.sub(r"[^a-zA-Z0-9\s-]", "", cocktail_name)
            safe_name = re.sub(r"\s+", "_", safe_name.strip())

            # Configure yt-dlp options
            ydl_opts = {
                "outtmpl": f"videos/{safe_name}.%(ext)s",
                "format": "best[height<=1080]",  # Download up to 1080p quality
                "quiet": True,  # Suppress most output
                "no_warnings": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Get video info to determine final filename
                info = ydl.extract_info(video_url, download=False)
                ext = info.get("ext", "mp4")
                filename = f"videos/{safe_name}.{ext}"

                # Download video
                ydl.download([video_url])

            print(f"  Downloaded video: {filename}")
            return filename

        except Exception as e:
            print(f"  Error downloading video for {cocktail_name}: {e}")
            return None

    def download_media_for_recipes(self, recipes):
        """Download media (images and videos) for a list of recipes"""
        print("Setting up media folders...")
        self.setup_media_folders()

        updated_recipes = []
        for recipe in recipes:
            print(f"Downloading media for {recipe['name']}...")

            # Create a copy of the recipe to avoid modifying the original
            updated_recipe = recipe.copy()

            # Download image and update path
            if recipe.get("image"):
                local_image_path = self.download_image(recipe["image"], recipe["name"])
                if local_image_path:
                    updated_recipe["local_image"] = local_image_path

            # Download video and update path
            if recipe.get("video"):
                local_video_path = self.download_video(recipe["video"], recipe["name"])
                if local_video_path:
                    updated_recipe["local_video"] = local_video_path

            updated_recipes.append(updated_recipe)

        print(f"Completed media download for {len(recipes)} recipes")
        return updated_recipes

    def scrape_all_recipes(
        self, output_format="json", max_cocktails=None, download_media=False
    ):
        """Scrape all recipes and save to file"""
        print("Getting cocktail links...")
        cocktail_links = self.get_cocktail_links()
        print(f"Found {len(cocktail_links)} cocktail links")

        if max_cocktails:
            cocktail_links = cocktail_links[:max_cocktails]
            print(f"Limiting to first {max_cocktails} cocktails")

        recipes = []
        successful = 0

        for i, cocktail_info in enumerate(cocktail_links[:max_cocktails]):
            print(
                f"Scraping {i+1}/{len(cocktail_links[:max_cocktails])}: {cocktail_info['name']}"
            )
            recipe = self.scrape_cocktail_recipe(
                cocktail_info["url"], cocktail_info["name"]
            )
            if recipe:
                recipe["category"] = cocktail_info["category"]
                recipe["views"] = cocktail_info.get("views")

                recipes.append(recipe)
                successful += 1
                print(f"  Successfully scraped {cocktail_info['name']}")
            else:
                print(f"  Failed to scrape {cocktail_info['name']}")

            # Be respectful - add delay between requests
            time.sleep(1)

        print(
            f"\nSuccessfully scraped {successful}/{len(cocktail_links[:max_cocktails]) if max_cocktails else len(cocktail_links)} recipes"
        )

        # Download media if enabled
        if download_media:
            print("\nDownloading media for all recipes...")
            recipes = self.download_media_for_recipes(recipes)

        # Save results
        if output_format.lower() == "json":
            filename = "iba_cocktail_recipes.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(recipes, f, indent=2, ensure_ascii=False)
        elif output_format.lower() == "csv":
            filename = "iba_cocktail_recipes.csv"
            with open(filename, "w", newline="", encoding="utf-8") as f:
                if recipes:
                    # Create flattened structure for CSV
                    fieldnames = [
                        "name",
                        "category",
                        "url",
                        "ingredients",
                        "method",
                        "preparation",
                        "glass",
                        "garnish",
                    ]
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for recipe in recipes:
                        # Convert list ingredients to string for CSV
                        recipe_copy = recipe.copy()
                        recipe_copy["ingredients"] = " | ".join(recipe["ingredients"])
                        writer.writerow(recipe_copy)

        print(f"Results saved to {filename}")
        return recipes


def main():
    scraper = IBACocktailScraper()

    # Test with all cocktails to verify parsing
    print("Testing with all cocktails...")
    recipes = scraper.scrape_all_recipes(
        output_format="json", max_cocktails=None, download_media=False
    )

    if recipes:
        print(f"\nSample recipe - {recipes[0]['name']}:")
        print(f"Category: {recipes[0]['category']}")
        print(f"Views: {recipes[0]['views']}")
        print(f"Ingredients: {recipes[0]['ingredients']}")
        print(f"Method: {recipes[0]['method']}")
        print(f"Garnish: {recipes[0]['garnish']}")
        print(f"Image: {recipes[0]['image'] if recipes[0]['image'] else 'None'}")
        print(f"Local Image: {recipes[0].get('local_image', 'None')}")
        print(f"Video: {recipes[0]['video'] if recipes[0]['video'] else 'None'}")
        print(f"Local Video: {recipes[0].get('local_video', 'None')}")

        # If the test looks good, ask user if they want to scrape all
        print(f"\nTest completed successfully! Found {len(recipes)} valid recipes.")
        print(
            "To scrape all cocktails, change max_cocktails=None in the main() function."
        )
    else:
        print("No recipes were successfully scraped. Check the parsing logic.")


if __name__ == "__main__":
    main()
