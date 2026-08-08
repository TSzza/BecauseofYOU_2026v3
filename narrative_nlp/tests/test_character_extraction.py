import unittest

from narrative_nlp.pipeline import NovelIndexer


class CharacterExtractionTests(unittest.TestCase):
    def profiles(self, text: str) -> set[str]:
        result = NovelIndexer(source_id="test").index_text(text)
        return {item["name"] for item in result["character_profiles"]}

    def test_title_match_does_not_absorb_sentence_prefix(self) -> None:
        names = self.profiles("大哥说，今天请何先生来，给你诊一诊。何先生随后离开。")
        self.assertIn("何", names)
        self.assertNotIn("天请何", names)

    def test_multi_character_name_before_title(self) -> None:
        names = self.profiles("我踩了古久先生的账簿。古久先生很不高兴。")
        self.assertIn("古久", names)

    def test_traditional_name_with_relational_context(self) -> None:
        names = self.profiles("趙貴翁的眼色便怪。我同趙貴翁有什麼仇？")
        self.assertIn("趙貴翁", names)

    def test_common_words_are_not_confirmed_characters(self) -> None:
        names = self.profiles("方法写得明白，因此后来大家都写着同样的话。他也胡涂过去，随后高声喝道。")
        self.assertFalse({"方法", "明白", "都写", "胡涂", "高声喝"} & names)

    def test_surname_question_is_not_a_person(self) -> None:
        names = self.profiles("问他姓什么，姓名籍贯有无凭据？")
        self.assertFalse({"什么", "名籍贯有"} & names)

    def test_gutenberg_offsets_reference_original_source_and_notes_are_excluded(self) -> None:
        raw = "header\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\n趙貴翁说道。趙貴翁离开。\n注釋\n齊莊公说道。\n*** END OF THE PROJECT GUTENBERG EBOOK X ***"
        result = NovelIndexer(source_id="test").index_text(raw)
        names = {item["name"] for item in result["character_profiles"]}
        self.assertIn("趙貴翁", names)
        self.assertNotIn("齊莊公", names)
        span = next(item for item in result["indexes"]["entity_mentions"] if item["text"] == "趙貴翁")
        self.assertEqual(raw[span["start"]:span["end"]], "趙貴翁")

    def test_candidates_do_not_create_character_lines(self) -> None:
        result = NovelIndexer(source_id="test").index_text("易子而食。易子而食。后来有人说道此事。")
        candidate_names = {item["surface"] for item in result["indexes"]["character_candidates"]}
        profile_names = {item["name"] for item in result["character_profiles"]}
        self.assertIn("易子而", candidate_names)
        self.assertNotIn("易子而", profile_names)
        self.assertNotIn("易子而", {line["character_id"] for line in result["character_lines"]})

    def test_mixed_chinese_latin_name_is_supported(self) -> None:
        self.assertIn("阿Q", self.profiles("阿Q说完便走。后来阿Q又回来了。"))
        self.assertIn("阿Ｑ", self.profiles("阿Ｑ说完便走。后来阿Ｑ又回来了。"))

    def test_adjacent_actions_merge_into_traceable_plot_event(self) -> None:
        result = NovelIndexer(source_id="test").index_text("阿Q说他要走。阿Q转身离开。第二天，阿Q回来了。")
        plot_events = result["world_line"]["plot_events"]
        merged = next(item for item in plot_events if len(item["member_world_event_ids"]) == 2)
        self.assertEqual(merged["raw_text"], "阿Q说他要走。阿Q转身离开。")
        self.assertEqual(len(merged["source_spans"]), 2)

    def test_unnamed_role_chain_remains_document_local_candidate(self) -> None:
        result = NovelIndexer(source_id="test").index_text("大哥说要出门。后来大哥回来了。")
        roles = result["character_resolution"]["unnamed_role_chains"]
        role = next(item for item in roles if item["surface"] == "大哥")
        self.assertEqual(role["scope"], "document_local")
        self.assertEqual(role["status"], "coreference_candidate")

    def test_short_surname_alias_is_candidate_not_automatic_merge(self) -> None:
        result = NovelIndexer(source_id="test").index_text("曹操说道此事。那位老爷本姓曹。曹操随后离开。")
        aliases = result["character_resolution"]["alias_candidates"]
        self.assertTrue(any(item["status"] == "candidate" for item in aliases))
        self.assertEqual(result["character_resolution"]["canonical_alias_groups"], [])

    def test_world_event_affect_keeps_source_evidence(self) -> None:
        result = NovelIndexer(source_id="test").index_text("阿Q非常害怕，手也发抖。阿Q随后离开。")
        event = next(item for item in result["world_line"]["events"] if item["event"]["affect"]["evidence_count"])
        evidence = event["event"]["affect"]["expressions"]
        self.assertTrue(any(item["emotion"] == "fear" for item in evidence))
        self.assertTrue(all(item["source_span"]["text"] in event["event"]["raw_text"] for item in evidence))

    def test_negation_changes_only_its_own_affect_evidence(self) -> None:
        result = NovelIndexer(source_id="test").index_text("阿Q并不高兴。后来阿Q终于高兴起来。")
        values = [
            evidence["vad"]["valence"]
            for event in result["world_line"]["events"]
            for evidence in event["event"]["affect"]["expressions"]
            if evidence["text"] == "高兴"
        ]
        self.assertEqual(len(values), 2)
        self.assertLess(values[0], 0.5)
        self.assertGreater(values[1], 0.5)

    def test_character_line_contains_continuous_affect_transition(self) -> None:
        result = NovelIndexer(source_id="test").index_text("阿Q很开心地大笑。随后阿Q害怕得发抖。")
        route = next(line for line in result["character_lines"] if line["items"])
        first, second = route["items"][:2]
        self.assertEqual(second["psychology"]["affect"]["before"], first["psychology"]["affect"]["after"])
        self.assertIn("affective_summary", route)

    def test_flashback_keeps_discourse_and_story_time_status(self) -> None:
        result = NovelIndexer(source_id="test").index_text("阿Q离开学校。多年以前，阿Q曾经住在这里。后来阿Q回来了。")
        flashback = next(item for item in result["world_line"]["events"] if "多年以前" in item["event"]["raw_text"])
        self.assertEqual(flashback["time"]["story_time_status"], "candidate")
        self.assertIn("discourse_sequence", flashback["time"])
        self.assertTrue(any(item["relation"] == "STORY_BEFORE" for item in result["world_line"]["temporal_relations"]))

    def test_explicit_dialogue_has_speaker_candidate(self) -> None:
        result = NovelIndexer(source_id="test").index_text("阿Q说道：“我很害怕。”后来阿Q离开。")
        dialogue = next(item for item in result["world_line"]["events"] if "害怕" in item["event"]["raw_text"])
        self.assertTrue(dialogue["event"]["discourse"]["quoted"])
        self.assertIsNotNone(dialogue["event"]["discourse"]["speaker_id"])

    def test_consistency_audit_covers_all_plot_members(self) -> None:
        result = NovelIndexer(source_id="test").index_text("阿Q说他要走。阿Q转身离开。第二天阿Q回来。")
        audit = result["indexes"]["consistency_audit"]
        self.assertEqual(audit["plot_event_reference_coverage"], 1.0)
        self.assertEqual(audit["unreferenced_world_events"], [])
        self.assertEqual(audit["status"], "ok")


if __name__ == "__main__":
    unittest.main()
