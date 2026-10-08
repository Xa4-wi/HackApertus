.PHONY: run dev test test-ui demo submission verify-submission model-pull model-serve dataset booklets ocr-setup evaluate-prepare evaluate report
run dev test test-ui demo submission verify-submission model-pull model-serve dataset booklets ocr-setup evaluate-prepare evaluate report:
	$(MAKE) -C track_2a $@
