import csv
from collections import OrderedDict

def extract_support_titres():
    support_titres = OrderedDict()  # To maintain order and remove duplicates
    
    try:
        with open('articles.csv', 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                support_titre = row['support_titre'].strip()
                if support_titre:  # Only add non-empty values
                    support_titres[support_titre] = True
            
        # Save to file
        with open('support_titres.txt', 'w', encoding='utf-8') as outfile:
            for support_titre in support_titres.keys():
                outfile.write(support_titre + '\n')
                
        print(f"Extracted {len(support_titres)} unique support_titre values to 'support_titres.txt'")
        
    except FileNotFoundError:
        print("Error: articles.csv file not found")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    extract_support_titres()