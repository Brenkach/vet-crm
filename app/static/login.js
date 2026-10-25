const loginForm = document.getElementById("login-form");
const loginError = loginForm.querySelector(".form-error");

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.hidden = true;
  const button = loginForm.querySelector("button");
  button.disabled = true;
  try {
    const data = new FormData(loginForm);
    const token = await api("/auth/login", {
      method: "POST",
      form: { username: data.get("email"), password: data.get("password") },
    });
    setToken(token.access_token);
    const me = await api("/users/me");
    location.href = homeFor(me.role);
  } catch (err) {
    showError(loginError, err);
  } finally {
    button.disabled = false;
  }
});
