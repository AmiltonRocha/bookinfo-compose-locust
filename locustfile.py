from locust import HttpUser, between, task


class ProductPageUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def abrir_product_page(self):
        self.client.get("/productpage?u=normal")
