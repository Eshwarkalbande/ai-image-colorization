
# --- GLOWING BUTTONS ---
# Upload Button
btn_up = tk.Button(root, text="↑ UPLOAD PHOTO", command=select_image, bg="#003d4d", fg="white", 
                activebackground=ACCENT_BLUE, activeforeground="black", font=("Segoe UI", 12, "bold"),
                bd=0, width=30, pady=12, cursor="hand2")
btn_up.pack(pady=15)

# Colorize Button
btn_go = tk.Button(root, text="★ START COLORIZATION", command=run_colorization, bg="#0e3311", fg="white", 
                activebackground=ACCENT_GREEN, activeforeground="black", font=("Segoe UI", 12, "bold"),
                bd=0, width=30, pady=12, cursor="hand2")
btn_go.pack(pady=5)