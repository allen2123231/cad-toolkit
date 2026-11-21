;;; Fenced execution, loaded AFTER the pinned dispatcher's command whitelist.
;;; Reactor callbacks only observe; commands execute from this explicit entry.
(defun mcp-toolkit-phase-write (request-id phase / file fp)
  (setq *mcp-toolkit-phase* phase)
  (setq file (strcat *mcp-ipc-dir* "toolkit-receipt-" request-id ".json"))
  (if (setq fp (open (strcat file ".tmp") "w"))
    (progn
      (write-line (strcat "{\"request_id\":\"" request-id "\",\"phase\":\"" phase
        "\",\"document_id\":\"" *mcp-toolkit-document-id* "\"}") fp)
      (close fp) (if (findfile file) (vl-file-delete file))
      (vl-file-rename (strcat file ".tmp") file)))
  (vl-catch-all-apply 'mcp-toolkit-context-write nil))

(defun c:mcp-dispatch (/ files file text request-id cmd result result-file old-osmode old-cmdecho)
  (setq files (vl-directory-files *mcp-ipc-dir* "autocad_mcp_cmd_*.json" 1))
  ;; Never choose arbitrarily among competing/legacy mailboxes.
  (if (= (length files) 1)
    (progn
      (setq file (strcat *mcp-ipc-dir* (car files)) text (mcp-read-file-lines file))
      (setq request-id (mcp-json-get-string text "request_id") cmd (mcp-json-get-string text "command"))
      (if (and request-id cmd)
        (progn
          (setq result-file (strcat *mcp-ipc-dir* "autocad_mcp_result_" request-id ".json"))
          (cond
            ((findfile (strcat *mcp-ipc-dir* "toolkit-recovery.json"))
              (vl-file-delete file)
              (mcp-write-result result-file request-id nil nil "RECOVERY_BARRIER_NOT_EXECUTED"))
            ((or (/= (mcp-json-get-number text "toolkit_protocol") 2)
                 (/= (mcp-json-get-number text "toolkit_hwnd") (vla-get-HWND (vlax-get-acad-object)))
                 (/= (mcp-json-get-string text "toolkit_document") *mcp-toolkit-document-id*))
              (vl-file-delete file)
              (mcp-write-result result-file request-id nil nil "TARGET_DOCUMENT_CHANGED_NOT_EXECUTED"))
            ((or *mcp-toolkit-native-busy* (> (getvar "CMDACTIVE") 0))
              (vl-file-delete file)
              (mcp-write-result result-file request-id nil nil "CAD_BUSY_NOT_EXECUTED"))
            (T
              (vl-file-delete file)
              (mcp-toolkit-phase-write request-id "claimed")
              (setq old-osmode (getvar "OSMODE") old-cmdecho (getvar "CMDECHO"))
              (setvar "OSMODE" 0) (setvar "CMDECHO" 0)
              (mcp-toolkit-phase-write request-id "executing")
              (setq result (vl-catch-all-apply 'mcp-dispatch-command (list cmd text)))
              ;; No ESC, retries, or implicit completion of interactive commands.
              (setvar "OSMODE" old-osmode) (setvar "CMDECHO" old-cmdecho)
              (if (vl-catch-all-error-p result) (setq result (cons nil (vl-catch-all-error-message result))))
              (if (= 1 (logand 1 (getvar "CMDACTIVE")))
                ;; The operation left an interactive prompt. Its modifications
                ;; are uncertain: do not claim completion or send ESC for it.
                (mcp-toolkit-phase-write request-id "waiting_input")
                (progn
                  (if (car result)
                    (mcp-write-result result-file request-id T (cdr result) nil)
                    (mcp-write-result result-file request-id nil nil (cdr result)))
                  (mcp-toolkit-phase-write request-id "completed")
                  (setq *mcp-toolkit-phase* "idle")
                  (vl-catch-all-apply 'mcp-toolkit-context-write nil)))))))))
  (princ))
(princ)
