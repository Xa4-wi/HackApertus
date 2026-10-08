.PHONY: run dev test test-ui submission verify-submission model-pull model-serve dataset booklets ocr-setup evaluate-prepare evaluate evaluate-score report check-endpoint
run dev test test-ui submission verify-submission model-pull model-serve dataset booklets ocr-setup evaluate-prepare evaluate evaluate-score report check-endpoint:
	$(MAKE) -C track_2a $@
