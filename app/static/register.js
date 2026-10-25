const registerForm = document.getElementById("register-form");
const registerError = registerForm.querySelector(".form-error");

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  registerError.hidden = true;
  const button = registerForm.querySelector("button");
  button.disabled = true;
  const data = new FormData(registerForm);
  try {
    await api("/auth/register", {
      method: "POST",
      json: { full_name: data.get("full_name"), email: data.get("email"), password: data.get("password") },
    });
    // Одразу входимо, щоб не вводити дані двічі
    const token = await api("/auth/login", {
      method: "POST",
      form: { username: data.get("email"), password: data.get("password") },
    });
    setToken(token.access_token);
    location.href = "client.html";
  } catch (err) {
    showError(registerError, err);
  } finally {
    button.disabled = false;
  }
});
