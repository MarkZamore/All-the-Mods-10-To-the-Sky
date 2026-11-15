import argparse
from pathlib import Path


parser = argparse.ArgumentParser(description="Prepare the native Sky localization smoke probe")
parser.add_argument("--base-agent", type=Path, default=Path("tools/PackData/CurseForge/Forge118SteamQaAgent.java"))
parser.add_argument("--installation", default="runtime-qa", choices=("runtime-qa", "runtime"))
parser.add_argument("output", type=Path)
args = parser.parse_args()
source = args.base_agent.read_text(encoding="utf-8-sig")
source = source.replace('root.resolve("runtime-qa")', f'root.resolve("{args.installation}")')
source = source.replace('toNanos(11)', 'toNanos(20)').replace('waitUntil("title", 240', 'waitUntil("title", 360')
start = source.index("            onClient(() -> { beginPublish()")
end = source.index("        } catch (Exception failure)", start)
source = source[:start] + """            waitUntil("localization data", 90, () -> onClient(() -> {
                Object questFile = type("dev.ftb.mods.ftbquests.client.ClientQuestFile").getField("INSTANCE").get(null);
                if (questFile == null || invoke(questFile, "getBase", new Class<?>[] { long.class },
                    Long.parseUnsignedLong("3BC0A50886A3222B", 16)) == null) return false;
                for (String id : patchouliSamples()) if (bookCategories(id).isEmpty()) return false;
                return true;
            }));
            event("locale_runtime", onClient(this::checkLocale));
            event("complete", Map.of("locale", "PASS"));
""" + source[end:]
start = source.index("    private void checkPermissions()")
source = source[:start] + """    private List<String> patchouliSamples() {
        return List.of("industrialforegoing:industrial_foregoing", "pneumaticcraft:book", "bigreactors:erguide",
            "justdirethings:justdirethingsbook", "productivebees:guide", "productivetrees:guide");
    }

    private Map<?,?> bookCategories(String id) throws Exception {
        Object registry = type("vazkii.patchouli.common.book.BookRegistry").getField("INSTANCE").get(null);
        Map<?,?> books = (Map<?,?>) field(registry.getClass(), "books").get(registry);
        Object book = books.entrySet().stream().filter(entry -> entry.getKey().toString().equals(id))
            .findFirst().orElseThrow(() -> new IllegalStateException("Book missing: " + id)).getValue();
        Object contents = invoke(book, "getContents");
        return (Map<?,?>) field(contents.getClass(), "categories").get(contents);
    }

    private Map<String, Object> checkLocale() throws Exception {
        String language = (String) invoke(invoke(client, "getLanguageManager"), "getSelected");
        boolean russian = worldName.endsWith("LocaleRu");
        require(language.equals(russian ? "ru_ru" : "en_us"), "Wrong runtime language: " + language);

        Object questFile = type("dev.ftb.mods.ftbquests.client.ClientQuestFile").getField("INSTANCE").get(null);
        Object quest = invoke(questFile, "getBase", new Class<?>[] { long.class },
            Long.parseUnsignedLong("3BC0A50886A3222B", 16));
        String title = (String) invoke(invoke(quest, "getTitle"), "getString");
        require(title.contains(russian ? "Добро пожаловать" : "Welcome"), "Unexpected localized quest title: " + title);

        Class<?> i18n = type("net.minecraft.client.resources.language.I18n");
        Map<String,String> expectedRu = Map.of(
            "ars_nouveau.alias.worn_notebook", "Потрёпанная записная книжка",
            "info_book.integrateddynamics.manual.introduction.text1", "В этом разделе",
            "book.neovitae.guide.rituals.ritual_regeneration.name", "Ритуал восстановления",
            "guide.herbsandharvest.aged_cheddar_desc", "Выдержанный чеддер",
            "The Extreme Book", "Справочник Extreme Reactors");
        int localized = 0;
        for (var sample : expectedRu.entrySet()) {
            if (!russian && sample.getKey().equals("The Extreme Book")) continue;
            Object text = invoke(i18n, null, "get", new Class<?>[] { String.class, Object[].class },
                sample.getKey(), new Object[0]);
            require(String.valueOf(text).contains(sample.getValue()) == russian, "Unexpected book translation " + sample.getKey());
            ++localized;
        }
        Map<String, Integer> bookCounts = new TreeMap<>();
        for (String id : patchouliSamples()) {
            Map<?,?> categories = bookCategories(id);
            boolean containsRussianCategory = false;
            for (Object category : categories.values()) {
                String name = (String) invoke(invoke(category, "getName"), "getString");
                containsRussianCategory |= name.codePoints().anyMatch(c -> Character.UnicodeScript.of(c) == Character.UnicodeScript.CYRILLIC);
            }
            require(containsRussianCategory == russian, "Unexpected Patchouli category language: " + id);
            bookCounts.put(id, categories.size());
        }
        return Map.of("language", language, "questTitle", title, "bookLanguageSamples", localized,
            "patchouliCategories", bookCounts, "patchouliRussian", russian);
    }

""" + source[start:]
print("Prepared two-language native probe")
args.output.write_text(
    source.replace("Forge118SteamQaAgent", "Forge118LocaleQaAgent"), encoding="utf-8", newline="\n")
