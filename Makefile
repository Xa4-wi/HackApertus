.PHONY: run dev test test-ui submission verify-submission model-pull model-serve dataset booklets ocr-setup evaluate-prepare evaluate report report-v2 check-endpoint
run dev test test-ui submission verify-submission model-pull model-serve dataset booklets ocr-setup evaluate-prepare evaluate report report-v2 check-endpoint:
	$(MAKE) -C track_2a $@
